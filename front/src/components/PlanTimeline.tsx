import { formatDuration, plural } from "../format";
import type { AnalysisResult } from "../types";

// Dos barras con la MISMA escala de tiempo: el video y los anuncios.
// Así se ve de un vistazo cuánto anuncio se paga por cuánto video.
export function PlanTimeline({ result }: { result: AnalysisResult }) {
  const scale = result.max_free_seconds;
  const videoPct = Math.min(100, (result.duration_seconds / scale) * 100);
  const adPct = (result.seconds_per_ad / scale) * 100;
  const ads = Array.from({ length: result.ads_required }, (_, i) => i);
  const n = result.ads_required;

  const label =
    `Tu video dura ${formatDuration(result.duration_seconds)}. ` +
    `Verás ${n} ${plural(n, "anuncio", "anuncios")} de ${result.seconds_per_ad} segundos.`;

  return (
    <div className="timeline" role="img" aria-label={label}>
      <div className="track-row">
        <span className="track-label">Tu video</span>
        <div>
          <div className="track">
            <div className="track-video" style={{ width: `${videoPct}%` }} />
          </div>
          <span className="track-note">{formatDuration(result.duration_seconds)}</span>
        </div>
      </div>

      <div className="track-row">
        <span className="track-label">Anuncios</span>
        <div>
          <div className="track">
            {ads.map((i) => (
              <div key={i} className="track-ad" style={{ width: `${adPct}%` }} />
            ))}
          </div>
          <span className="track-note">
            {n} {plural(n, "anuncio", "anuncios")} de {result.seconds_per_ad} s, en total{" "}
            {formatDuration(result.total_ad_seconds)}
          </span>
        </div>
      </div>
    </div>
  );
}
