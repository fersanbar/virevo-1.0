
import { useState } from "react";
import { analyzeVideo, validateFile } from "./api";
import { AdPlayer } from "./components/AdPlayer";
import { Dropzone } from "./components/Dropzone";
import { PlanTimeline } from "./components/PlanTimeline";
import { SubtitleEditor } from "./components/SubtitleEditor";
import { TranscriptionStep } from "./components/TranscriptionStep";
import { formatDuration, plural } from "./format";
import type { AnalysisResult, Segment } from "./types";

type Phase =
  | { name: "idle" }
  | { name: "uploading"; fileName: string; progress: number }
  | { name: "plan"; file: File; result: AnalysisResult }
  | { name: "ads"; file: File; result: AnalysisResult; sessionId: string }
  | { name: "transcribe"; file: File; sessionId: string }
  | { name: "editor"; file: File; sessionId: string; segments: Segment[] }
  | { name: "error"; message: string };

const STEPS = ["Subir video", "Ver anuncios", "Tus subtítulos"];

function currentStep(phase: Phase): number {
  switch (phase.name) {
    case "ads":
      return 1;
    case "transcribe":
    case "editor":
      return 2;
    default:
      return 0;
  }
}

export default function App() {
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const step = currentStep(phase);

  async function handleFile(file: File) {
    const problem = validateFile(file);

    if (problem) {
      setPhase({ name: "error", message: problem });
      return;
    }

    setPhase({ name: "uploading", fileName: file.name, progress: 0 });

    try {
      const result = await analyzeVideo(file, (progress) =>
        setPhase({
          name: "uploading",
          fileName: file.name,
          progress,
        }),
      );

      setPhase({ name: "plan", file, result });
    } catch (err) {
      setPhase({
        name: "error",
        message:
          err instanceof Error
            ? err.message
            : "Algo salió mal. Intenta de nuevo.",
      });
    }
  }

  const reset = () => setPhase({ name: "idle" });

  return (
    <div className="app">
      <header className="site-header">
        <a
          className="brand"
          href="#inicio"
          aria-label="Virevo, inicio"
          onClick={(event) => {
            event.preventDefault();
            reset();
          }}
        >
          <span className="brand-symbol" aria-hidden="true">
            <span />
          </span>
          <span>virevo</span>
        </a>

        <div className="header-note">
          <span className="status-dot" />
          Herramientas para creadores
        </div>
      </header>

      <main id="inicio">
        <section className="hero">
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            TU VIDEO. UN NUEVO NIVEL.
          </div>

          <h1>
            Tus videos.
            <br />
            <span className="heading-accent">Listos para crear.</span>
          </h1>

          <p className="hero-description">
            Genera subtítulos para tus videos de forma sencilla.
            Sube tu archivo, completa el proceso y prepara tus subtítulos
            para el siguiente paso.
          </p>
        </section>

        <nav className="steps-nav" aria-label="Progreso del proceso">
          <ol className="steps">
            {STEPS.map((label, i) => (
              <li
                key={label}
                aria-current={i === step ? "step" : undefined}
                className={[
                  i < step ? "is-done" : "",
                  i === step ? "is-current" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="step-number">
                  {i < step ? "✓" : `0${i + 1}`}
                </span>
                <span>{label}</span>
              </li>
            ))}
          </ol>
        </nav>

        <div className="panel">
          {phase.name === "idle" && (
            <section>
              <div className="section-heading">
                <span className="section-kicker">EMPIEZA AQUÍ</span>
                <h2>Convierte tu video en contenido listo para publicar.</h2>
                <p className="lead">
                  Sube tu video y descubre cuántos anuncios necesitas ver
                  para desbloquear la generación de subtítulos.
                </p>
              </div>

              <Dropzone onFile={handleFile} />

              <div className="trust-row">
                <span>
                  <span className="trust-icon">↗</span>
                  Proceso sencillo
                </span>
                <span>
                  <span className="trust-icon">✳</span>
                  Subtítulos editables
                </span>
                <span>
                  <span className="trust-icon">↓</span>
                  Listos para exportar
                </span>
              </div>
            </section>
          )}

          {phase.name === "uploading" && (
            <section>
              <span className="section-kicker">PROCESANDO ARCHIVO</span>
              <h2>
                {phase.progress < 100
                  ? "Tu video está en camino."
                  : "Analizando la duración."}
              </h2>
              <p className="lead file-name">{phase.fileName}</p>

              <div
                className="progress"
                role="progressbar"
                aria-label="Progreso de carga"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={phase.progress}
              >
                <div
                  className="progress-fill"
                  style={{ width: `${phase.progress}%` }}
                />
              </div>

              <div className="progress-meta">
                <span>
                  {phase.progress < 100 ? "Subiendo tu archivo" : "Casi listo"}
                </span>
                <strong>{phase.progress}%</strong>
              </div>
            </section>
          )}

          {phase.name === "plan" && phase.result.allowed && (
            <section>
              <span className="section-kicker">ANÁLISIS COMPLETADO</span>
              <h2>
                Tu video dura{" "}
                <span className="heading-accent">
                  {formatDuration(phase.result.duration_seconds)}
                </span>
              </h2>

              <p className="lead">
                Para desbloquear tus subtítulos, necesitas ver{" "}
                <strong>{phase.result.ads_required}</strong>{" "}
                {plural(phase.result.ads_required, "anuncio", "anuncios")} de{" "}
                <strong>{phase.result.seconds_per_ad} segundos</strong>.
              </p>

              <div className="timeline-card">
                <PlanTimeline result={phase.result} />
                <p className="muted">
                  Ambas barras utilizan la misma escala de tiempo.
                </p>
              </div>

              <div className="actions">
                <button
                  className="btn"
                  onClick={() => {
                    const sessionId = phase.result.session_id;

                    if (sessionId) {
                      setPhase({
                        name: "ads",
                        file: phase.file,
                        result: phase.result,
                        sessionId,
                      });
                    }
                  }}
                  disabled={!phase.result.session_id}
                >
                  Continuar <span aria-hidden="true">↗</span>
                </button>

                <button className="btn btn-secondary" onClick={reset}>
                  Elegir otro video
                </button>
              </div>
            </section>
          )}

          {phase.name === "plan" && !phase.result.allowed && (
            <section>
              <span className="section-kicker">LÍMITE DEL PLAN</span>
              <h2>Este video supera la duración permitida.</h2>
              <p className="lead">
                {phase.result.reason} Tu video dura{" "}
                {formatDuration(phase.result.duration_seconds)}. Prueba con
                un archivo más corto o recórtalo para continuar.
              </p>

              <div className="actions">
                <button className="btn" onClick={reset}>
                  Elegir otro video
                </button>
              </div>
            </section>
          )}

          {phase.name === "ads" && (
            <section>
              <span className="section-kicker">UN PASO MÁS</span>
              <h2>Tus subtítulos están cada vez más cerca.</h2>
              <p className="lead">
                Completa los anuncios para continuar con la generación.
              </p>

              <AdPlayer
                sessionId={phase.sessionId}
                count={phase.result.ads_required}
                secondsEach={phase.result.seconds_per_ad}
                onFinished={() =>
                  setPhase({
                    name: "transcribe",
                    file: phase.file,
                    sessionId: phase.sessionId,
                  })
                }
              />
            </section>
          )}

          {phase.name === "transcribe" && (
            <section>
              <span className="section-kicker">GENERANDO SUBTÍTULOS</span>
              <TranscriptionStep
                sessionId={phase.sessionId}
                onDone={(segments) =>
                  setPhase({
                    name: "editor",
                    file: phase.file,
                    sessionId: phase.sessionId,
                    segments,
                  })
                }
              />
            </section>
          )}

          {phase.name === "editor" && (
            <section>
              <span className="section-kicker">TU CONTENIDO, A TU MANERA</span>
              <SubtitleEditor
                file={phase.file}
                sessionId={phase.sessionId}
                initialSegments={phase.segments}
                onRestart={reset}
              />
            </section>
          )}

          {phase.name === "error" && (
            <section>
              <span className="section-kicker">ALGO NO SALIÓ COMO ESPERÁBAMOS</span>
              <h2>Vamos a intentarlo de nuevo.</h2>
              <p className="error" role="alert">
                {phase.message}
              </p>

              <div className="actions">
                <button className="btn" onClick={reset}>
                  Volver a empezar <span aria-hidden="true">↗</span>
                </button>
              </div>
            </section>
          )}
        </div>

        <footer className="site-footer">
          <span className="footer-brand">virevo<span>.</span></span>
          <span>Tus videos. Listos para crear.</span>
        </footer>
      </main>
    </div>
  );
}
