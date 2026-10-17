import { useEffect, useState } from "react";
import { getExport, srtDownloadUrl, startExport, videoDownloadUrl } from "../api";

interface Props {
  sessionId: string;
  dirty: boolean; // hay cambios sin guardar
  ensureSaved: () => Promise<boolean>;
}

type Phase = "idle" | "working" | "ready" | "error";

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Algo salió mal. Intenta de nuevo.";
}

export function ExportPanel({ sessionId, dirty, ensureSaved }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  // Si el usuario edita después de crear el video, ese video ya no coincide con el texto.
  useEffect(() => {
    if (dirty && phase === "ready") setPhase("idle");
  }, [dirty, phase]);

  async function create() {
    setError(null);
    if (!(await ensureSaved())) return; // el editor muestra su propio error
    setPhase("working");
    try {
      const state = await startExport(sessionId);
      if (state.status === "done") {
        setPhase("ready");
      } else if (state.status === "error") {
        setError(state.message ?? "No pudimos crear el video.");
        setPhase("error");
      }
      // Si sigue en "processing", la consulta periódica de abajo se encarga.
    } catch (err) {
      setError(messageOf(err));
      setPhase("error");
    }
  }

  useEffect(() => {
    if (phase !== "working") return;
    let cancelled = false;
    const id = window.setInterval(async () => {
      try {
        const state = await getExport(sessionId);
        if (cancelled) return;
        if (state.status === "done") {
          window.clearInterval(id);
          setPhase("ready");
        } else if (state.status === "error") {
          window.clearInterval(id);
          setError(state.message ?? "No pudimos crear el video.");
          setPhase("error");
        }
      } catch (err) {
        if (cancelled) return;
        window.clearInterval(id);
        setError(messageOf(err));
        setPhase("error");
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [phase, sessionId]);

  return (
    <div className="export">
      <h2>Descargar</h2>

      {phase === "working" ? (
        <>
          <p className="lead">
            Incrustando los subtítulos en tu video. Puede tardar unos minutos, según su duración.
            Mantén esta pestaña abierta.
          </p>
          <div className="progress progress-indeterminate" role="progressbar" aria-label="Creando el video">
            <div className="progress-fill" />
          </div>
        </>
      ) : (
        <>
          <p className="lead">
            Crea un video con los subtítulos incrustados, o descarga solo el archivo .srt para subirlo
            a YouTube u otra plataforma. Guardamos tus cambios automáticamente antes de crear el video.
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="actions">
            {phase === "ready" ? (
              <a className="btn" href={videoDownloadUrl(sessionId)} download>
                Descargar video con subtítulos
              </a>
            ) : (
              <button className="btn" onClick={create}>
                {phase === "error" ? "Reintentar" : "Crear video con subtítulos"}
              </button>
            )}
            {dirty ? (
              <button className="btn btn-secondary" disabled>
                Descargar .srt (guarda primero)
              </button>
            ) : (
              <a className="btn btn-secondary" href={srtDownloadUrl(sessionId)} download>
                Descargar .srt
              </a>
            )}
          </div>
        </>
      )}
    </div>
  );
}
