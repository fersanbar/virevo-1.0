// Misma forma que la respuesta de POST /videos/analizar en el backend.
export interface AnalysisResult {
  session_id: string | null; // null cuando el video no entra al plan gratis
  duration_seconds: number;
  max_free_seconds: number;
  allowed: boolean;
  ads_required: number;
  seconds_per_ad: number;
  total_ad_seconds: number;
  reason: string;
}

// Estado de la sesión de anuncios, tal como lo reporta el servidor.
export interface SessionState {
  ads_required: number;
  ads_completed: number;
  seconds_per_ad: number;
  unlocked: boolean;
  ad_in_progress: boolean;
  ad_seconds_left: number | null;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
}

export type TranscriptStatus = "none" | "processing" | "done" | "error";

export interface SubtitlesState {
  status: TranscriptStatus;
  message: string | null;
  segments: Segment[] | null;
}

export type Language = "es" | "en" | null; // null = detectar automáticamente

export interface ExportState {
  status: TranscriptStatus; // mismos estados: none | processing | done | error
  message: string | null;
}
