import { useEffect, useRef, useState } from "react";
import { getSubtitles, startTranscription } from "../api";
import type { Language, Segment } from "../types";

interface Props {
  sessionId: string;
  onDone: (segments: Segment[]) => void;
}

type Choice = "es" | "en" | "auto";

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Algo salió mal. Intenta de nuevo.";
}

export function TranscriptionStep({ sessionId, onDone }: Props) {
  const [choice, setChoice] = useState<Choice>("es");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // onDone cambia en cada render del padre; lo guardamos en una referencia
  // para no reiniciar la consulta periódica cada vez.
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  async function start() {
    setError(null);
    setWorking(true);
    const language: Language = choice === "auto" ? null : choice;
    try {
      const state = await startTranscription(sessionId, language);
      if (state.status === "done" && state.segments) {
        onDoneRef.current(state.segments);
      } else if (state.status === "error") {
        setWorking(false);
        setError(state.message ?? "No pudimos generar los subtítulos.");
      }
      // Si sigue en "processing", la consulta periódica de abajo se encarga.
    } catch (err) {
      setWorking(false);
      setError(messageOf(err));
    }
  }

  // Mientras se transcribe, preguntamos al servidor cada 2 segundos.
  useEffect(() => {
    if (!working) return;
    let cancelled = false;
    const id = window.setInterval(async () => {
      try {
        const state = await getSubtitles(sessionId);
        if (cancelled) return;
        if (state.status === "done" && state.segments) {
          window.clearInterval(id);
          onDoneRef.current(state.segments);
        } else if (state.status === "error") {
          window.clearInterval(id);
          setWorking(false);
          setError(state.message ?? "No pudimos generar los subtítulos.");
        }
      } catch (err) {
        if (cancelled) return;
        window.clearInterval(id);
        setWorking(false);
        setError(messageOf(err));
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [working, sessionId]);

  if (working) {
    return (
      <section>
        <h1>Generando tus subtítulos</h1>
        <p className="lead">Puede tardar un par de minutos, según la duración del video. Mantén esta pestaña abierta.</p>
        <div className="progress progress-indeterminate" role="progressbar" aria-label="Generando subtítulos">
          <div className="progress-fill" />
        </div>
      </section>
    );
  }

  return (
    <section>
      <h1>Anuncios completados</h1>
      <p className="lead">Elige el idioma en el que hablas en el video y generamos tus subtítulos.</p>
      <div className="field">
        <label htmlFor="idioma">Idioma del video</label>
        <select id="idioma" value={choice} onChange={(e) => setChoice(e.target.value as Choice)}>
          <option value="es">Español</option>
          <option value="en">English</option>
          <option value="auto">Detectar automáticamente</option>
        </select>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="btn" onClick={start}>
          {error ? "Reintentar" : "Generar subtítulos"}
        </button>
      </div>
    </section>
  );
}
