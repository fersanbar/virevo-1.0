"""Incrusta los subtítulos en el video con FFmpeg (filtro 'ass', que usa libass)."""
import os
import subprocess
from pathlib import Path

from app.media import VideoInvalidoError, get_video_size
from app.subtitles import build_ass


class ExportError(Exception):
    """El mensaje está pensado para mostrarse al usuario."""


def burn_subtitles(video_path: str | Path, segments: list[dict], out_path: str | Path) -> None:
    video_path = Path(video_path).resolve()
    out_path = Path(out_path).resolve()
    tmp_out = out_path.with_name(out_path.stem + ".part.mp4")  # no se sirve hasta que termine
    ass_path = video_path.with_suffix(".ass")

    try:
        width, height = get_video_size(str(video_path))
        ass_path.write_text(build_ass(segments, width, height), encoding="utf-8")
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
            # Se usa el nombre sin ruta (y se ejecuta dentro de su carpeta) para evitar
            # los problemas de rutas con ":" y "\" de Windows dentro de los filtros de FFmpeg.
            "-vf", f"ass={ass_path.name}",
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(tmp_out),
        ]
        subprocess.run(cmd, capture_output=True, timeout=1800, check=True, cwd=ass_path.parent)
        os.replace(tmp_out, out_path)
    except VideoInvalidoError as exc:
        raise ExportError(str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        if "No such filter" in stderr:
            raise ExportError(
                "Tu FFmpeg no incluye soporte de subtítulos (libass). Instala la versión completa."
            ) from exc
        raise ExportError("No pudimos crear el video con subtítulos.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExportError("Crear el video tardó demasiado. Intenta con un video más corto.") from exc
    finally:
        ass_path.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)
