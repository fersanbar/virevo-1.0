"""Lectura de metadatos del video con ffprobe (viene incluido con FFmpeg)."""
import json
import subprocess


class VideoInvalidoError(Exception):
    pass


def get_duration_seconds(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=True
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            KeyError, ValueError, json.JSONDecodeError) as exc:
        raise VideoInvalidoError("El archivo no parece ser un video válido.") from exc


def get_video_size(path: str) -> tuple[int, int]:
    """Ancho y alto del video TAL COMO SE VE (los videos de celular suelen traer rotación)."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        stream = json.loads(result.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        rotation = (stream.get("tags") or {}).get("rotate")
        for side in stream.get("side_data_list") or []:
            if "rotation" in side:
                rotation = side["rotation"]
        rotation = int(float(rotation)) if rotation is not None else 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError, IndexError,
            ValueError, TypeError, json.JSONDecodeError) as exc:
        raise VideoInvalidoError("No pudimos leer el tamaño del video.") from exc
    if abs(rotation) % 180 == 90:  # video girado 90/270 grados: ancho y alto se intercambian
        width, height = height, width
    return width, height
