"""Extrae el audio de un video con FFmpeg, listo para mandarlo a transcribir."""
import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    """El mensaje está pensado para mostrarse al usuario."""


def extract_audio(video_path: str | Path, out_path: str | Path) -> None:
    # Mono, 16 kHz y 32 kbps: suficiente para voz y muy ligero (15 min ~ 3.6 MB).
    # Los proveedores aceptan archivos de hasta ~25 MB, por eso no mandamos el video.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        "-f", "mp3", str(out_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        if "does not contain any stream" in stderr:
            raise AudioExtractionError("El video no tiene pista de audio.") from exc
        raise AudioExtractionError("No pudimos extraer el audio del video.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionError("Extraer el audio tardó demasiado. Intenta de nuevo.") from exc
