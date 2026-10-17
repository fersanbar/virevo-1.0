import { useEffect, useMemo, useRef, useState } from "react";
import { saveSubtitles } from "../api";
import { captionStyle, maxCharsPerLine, singleLineCues } from "../captions";
import type { Segment } from "../types";
import { ExportPanel } from "./ExportPanel";

interface Props {
  file: File;
  sessionId: string;
  initialSegments: Segment[];
  onRestart: () => void;
}

interface Row extends Segment {
  id: number;
}

type SaveStatus = "saved" | "dirty" | "saving" | "error";

const toRows = (segments: Segment[]): Row[] => segments.map((s, i) => ({ ...s, id: i }));

function clock(seconds: number): string {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const STATUS_TEXT: Record<SaveStatus, string> = {
  saved: "Todo guardado",
  dirty: "Cambios sin guardar",
  saving: "Guardando...",
  error: "No se pudo guardar",
};

const MAX_VIDEO_HEIGHT = 460;

export function SubtitleEditor({ file, sessionId, initialSegments, onRestart }: Props) {
  const [rows, setRows] = useState<Row[]>(() => toRows(initialSegments));
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [available, setAvailable] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [status, setStatus] = useState<SaveStatus>("saved");
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  // El video se reproduce desde tu propio archivo; no lo descargamos del servidor.
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setVideoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Ancho disponible para el video; se actualiza si cambia el tamaño de la ventana.
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setAvailable(el.clientWidth));
    observer.observe(el);
    setAvailable(el.clientWidth);
    return () => observer.disconnect();
  }, [videoUrl, videoFailed]);

  // Tamaño con el que se ve el video: respeta su proporción (horizontal o vertical).
  const box =
    natural && available > 0
      ? (() => {
          const scale = Math.min(available / natural.w, MAX_VIDEO_HEIGHT / natural.h);
          return { w: Math.round(natural.w * scale), h: Math.round(natural.h * scale) };
        })()
      : null;

  const active = rows.find((r) => currentTime >= r.start && currentTime < r.end);

  // Igual que en el video final: cada frase se parte en trozos de UNA línea.
  const cues = useMemo(
    () => (box ? singleLineCues(rows, maxCharsPerLine(box.w, box.h)) : []),
    [rows, box?.w, box?.h], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const activeCue = cues.find((c) => currentTime >= c.start && currentTime < c.end);

  function edit(id: number, text: string) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, text } : r)));
    setStatus("dirty");
  }

  function remove(id: number) {
    setRows((rs) => rs.filter((r) => r.id !== id));
    setStatus("dirty");
  }

  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    setCurrentTime(seconds);
  }

  function playFrom(row: Row) {
    seekTo(row.start);
    videoRef.current?.play().catch(() => undefined); // algunos formatos no se reproducen en el navegador
  }

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) video.play().catch(() => undefined);
    else video.pause();
  }

  async function save(): Promise<boolean> {
    setStatus("saving");
    setError(null);
    // Un subtítulo vacío equivale a borrarlo.
    const cleaned = rows
      .filter((r) => r.text.trim() !== "")
      .map(({ start, end, text }) => ({ start, end, text: text.trim() }));
    try {
      const state = await saveSubtitles(sessionId, cleaned);
      if (state.segments) setRows(toRows(state.segments));
      setStatus("saved");
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Algo salió mal. Intenta de nuevo.");
      setStatus("error");
      return false;
    }
  }

  async function ensureSaved(): Promise<boolean> {
    return status === "saved" ? true : save();
  }

  const canSave = status === "dirty" || status === "error";

  return (
    <section>
      <h1>Revisa tus subtítulos</h1>
      <p className="lead">Reproduce el video, corrige el texto que haga falta y guarda. Toca la hora de un subtítulo para saltar a ese momento.</p>

      {videoUrl && !videoFailed ? (
        <div className="editor-stage" ref={stageRef}>
          <div
            className="editor-video"
            style={box ? { width: box.w, height: box.h } : { width: "100%", aspectRatio: "16 / 9" }}
          >
            <video
              ref={videoRef}
              src={videoUrl}
              playsInline
              onClick={togglePlay}
              onLoadedMetadata={(e) => {
                setNatural({ w: e.currentTarget.videoWidth, h: e.currentTarget.videoHeight });
                setDuration(e.currentTarget.duration);
              }}
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onError={() => setVideoFailed(true)}
            />
            {activeCue && box && (
              <div className="caption" style={captionStyle(box.w, box.h)}>
                {activeCue.text}
              </div>
            )}
          </div>
          <div className="player-bar" style={box ? { width: box.w } : undefined}>
            <button className="btn btn-small" onClick={togglePlay}>
              {playing ? "Pausar" : "Reproducir"}
            </button>
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.1}
              value={Math.min(currentTime, duration || 0)}
              onChange={(e) => seekTo(Number(e.target.value))}
              aria-label="Posición del video"
            />
            <span className="player-time">
              {clock(currentTime)} / {clock(duration)}
            </span>
          </div>
        </div>
      ) : (
        videoFailed && (
          <p className="muted">Tu navegador no puede reproducir este formato de video, pero puedes editar el texto igual.</p>
        )
      )}

      <div className="editor-bar">
        <button className="btn" onClick={() => void save()} disabled={!canSave}>
          Guardar cambios
        </button>
        <span className="save-status" aria-live="polite">
          {STATUS_TEXT[status]}
        </span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {rows.length === 0 ? (
        <p className="muted">No quedan subtítulos.</p>
      ) : (
        <ol className="segments">
          {rows.map((row) => (
            <li key={row.id} className={`segment${active?.id === row.id ? " is-active" : ""}`}>
              <button
                className="seg-time"
                onClick={() => playFrom(row)}
                disabled={videoFailed}
                aria-label={`Ir al minuto ${clock(row.start)}`}
              >
                {clock(row.start)}
              </button>
              <textarea
                rows={2}
                maxLength={500}
                value={row.text}
                aria-label={`Subtítulo del minuto ${clock(row.start)}`}
                onChange={(e) => edit(row.id, e.target.value)}
              />
              <button className="seg-remove" onClick={() => remove(row.id)}>
                Quitar
              </button>
            </li>
          ))}
        </ol>
      )}

      {rows.length > 0 && (
        <ExportPanel
          sessionId={sessionId}
          dirty={status !== "saved"}
          ensureSaved={ensureSaved}
        />
      )}

      <div className="actions">
        <button className="btn btn-secondary" onClick={onRestart}>
          Subir otro video
        </button>
      </div>
    </section>
  );
}
