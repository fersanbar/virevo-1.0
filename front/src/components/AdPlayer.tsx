import { useEffect, useState } from "react";
import { ApiError, completeAd, startAd } from "../api";

interface Props {
  sessionId: string;
  count: number;
  secondsEach: number;
  onFinished: () => void;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Algo salió mal. Intenta de nuevo.";
}

// Anuncio SIMULADO, pero con validación real: el servidor mide el tiempo.
// La cuenta regresiva de aquí es solo visual; si el navegador la acelera o se
// salta, el servidor rechaza "completar" hasta que pase el tiempo de verdad.
export function AdPlayer({ sessionId, count, secondsEach, onFinished }: Props) {
  const [index, setIndex] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // 1) Al empezar cada anuncio, el servidor anota la hora de inicio y nos dice cuánto falta.
  useEffect(() => {
    let cancelled = false;
    startAd(sessionId)
      .then((state) => {
        if (!cancelled) setRemaining(Math.ceil(state.ad_seconds_left ?? secondsEach));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(messageOf(err));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, index, attempt, secondsEach]);

  // 2) Cuenta regresiva en pantalla. Al llegar a 0 pedimos al servidor que valide.
  useEffect(() => {
    if (remaining === null || error) return;
    if (remaining <= 0) {
      void finishAd();
      return;
    }
    const id = window.setTimeout(() => setRemaining((r) => (r === null ? r : r - 1)), 1000);
    return () => window.clearTimeout(id);
  }, [remaining, error]);

  async function finishAd() {
    try {
      const state = await completeAd(sessionId);
      if (state.unlocked) {
        onFinished();
        return;
      }
      setRemaining(null);
      setIndex((i) => i + 1);
    } catch (err) {
      if (err instanceof ApiError && err.secondsLeft !== undefined && err.secondsLeft <= 3) {
        // Diferencia mínima de reloj: esperamos lo que el servidor dice que falta.
        setRemaining(Math.max(1, Math.ceil(err.secondsLeft)));
      } else {
        setError(messageOf(err));
      }
    }
  }

  function retry() {
    setError(null);
    setRemaining(null);
    setAttempt((a) => a + 1);
  }

  const progress =
    remaining === null ? 0 : ((secondsEach - Math.max(0, remaining)) / secondsEach) * 100;

  return (
    <div>
      <p className="ad-status" aria-live="polite">
        Anuncio {index + 1} de {count}
      </p>
      <div className="ad-frame">
        <span className="ad-badge">Anuncio</span>
        <div>
          <div className="ad-count" role="timer">
            {remaining === null ? "…" : Math.max(0, remaining)}
          </div>
          <div className="ad-unit">segundos restantes</div>
        </div>
      </div>
      <div className="progress" aria-hidden="true">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      {error ? (
        <>
          <p className="error" role="alert">
            {error}
          </p>
          <button className="btn" onClick={retry}>
            Reintentar
          </button>
        </>
      ) : (
        <p className="muted">Mantén esta pestaña abierta. Tus subtítulos se desbloquean al terminar.</p>
      )}
    </div>
  );
}
