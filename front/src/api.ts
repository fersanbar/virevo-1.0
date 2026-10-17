import type {
  AnalysisResult,
  ExportState,
  Language,
  Segment,
  SessionState,
  SubtitlesState,
} from "./types";

// Estos límites repiten los del backend (app/main.py) solo para avisar rápido
// al usuario. El servidor siempre vuelve a validar.
const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".avi"];
const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Formato no soportado. Usa MP4, MOV, MKV, WEBM o AVI.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "El archivo supera los 500 MB. Elige un video más ligero.";
  }
  return null;
}

type ApiBody = Partial<AnalysisResult> & { detail?: unknown };

// Usamos XMLHttpRequest (y no fetch) porque fetch no reporta el progreso de subida.
export function analyzeVideo(
  file: File,
  onProgress: (percent: number) => void,
): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiUrl("/api/videos/analizar")}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      let body: ApiBody | null = null;
      try {
        body = JSON.parse(xhr.responseText) as ApiBody;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve(body as AnalysisResult);
      } else {
        const detail =
          typeof body?.detail === "string" ? body.detail : undefined;
        reject(
          new Error(
            detail ?? "No pudimos analizar el video. Intenta de nuevo.",
          ),
        );
      }
    };

    xhr.onerror = () =>
      reject(
        new Error(
          "No hay conexión con el servidor. Revisa que el backend esté corriendo.",
        ),
      );

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

// --- Llamadas a las sesiones (anuncios y subtítulos) ---

export class ApiError extends Error {
  secondsLeft?: number;

  constructor(message: string, secondsLeft?: number) {
    super(message);
    this.secondsLeft = secondsLeft;
  }
}

async function request<T>(
  url: string,
  method: "GET" | "POST" | "PUT",
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(url), {
      method,
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "No hay conexión con el servidor. Revisa que el backend esté corriendo.",
    );
  }
  const data = (await response.json().catch(() => null)) as
    | (T & { detail?: unknown; seconds_left?: number })
    | null;
  if (!response.ok) {
    // Los errores de validación de FastAPI traen una lista en "detail"; solo mostramos textos.
    const detail = typeof data?.detail === "string" ? data.detail : undefined;
    throw new ApiError(
      detail ?? "Algo salió mal. Intenta de nuevo.",
      data?.seconds_left,
    );
  }
  return data as T;
}

// El servidor anota cuándo empezó el anuncio.
export const startAd = (sessionId: string) =>
  request<SessionState>(`/api/sesiones/${sessionId}/anuncios/iniciar`, "POST");

// El servidor revisa su propio reloj; si no pasó el tiempo, responde con error.
export const completeAd = (sessionId: string) =>
  request<SessionState>(
    `/api/sesiones/${sessionId}/anuncios/completar`,
    "POST",
  );

// Solo funciona si el servidor confirma que se vieron todos los anuncios.
export const startTranscription = (sessionId: string, language: Language) =>
  request<SubtitlesState>(`/api/sesiones/${sessionId}/transcribir`, "POST", {
    idioma: language,
  });

export const getSubtitles = (sessionId: string) =>
  request<SubtitlesState>(`/api/sesiones/${sessionId}/subtitulos`, "GET");

export const saveSubtitles = (sessionId: string, segments: Segment[]) =>
  request<SubtitlesState>(`/api/sesiones/${sessionId}/subtitulos`, "PUT", {
    segments,
  });

// --- Video con subtítulos incrustados y descargas ---

export const startExport = (sessionId: string) =>
  request<ExportState>(`/api/sesiones/${sessionId}/exportar`, "POST");

export const getExport = (sessionId: string) =>
  request<ExportState>(`/api/sesiones/${sessionId}/exportacion`, "GET");

export const videoDownloadUrl = (sessionId: string) =>
  apiUrl(`/api/sesiones/${sessionId}/descargar/video`);

export const srtDownloadUrl = (sessionId: string) =>
  apiUrl(`/api/sesiones/${sessionId}/descargar/srt`);
