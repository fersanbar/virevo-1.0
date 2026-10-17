"""Prueba rápida del proveedor de transcripción, sin abrir la app.

Uso (desde la carpeta virevo-backend):
    python -m app.probar ruta/al/video.mp4 [es|en]
"""
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.audio import AudioExtractionError, extract_audio  # noqa: E402
from app.transcription import TranscriptionError, get_transcriber  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python -m app.probar ruta/al/video.mp4 [es|en]")
        return 1
    video = Path(sys.argv[1])
    language = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.mp3"
            extract_audio(video, audio)
            segments = get_transcriber().transcribe(audio, language)
    except (AudioExtractionError, TranscriptionError) as exc:
        print(f"Error: {exc}")
        return 1
    for s in segments:
        print(f"[{s.start:7.2f} -> {s.end:7.2f}] {s.text}")
    print(f"\n{len(segments)} subtítulos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
