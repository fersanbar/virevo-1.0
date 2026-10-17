"""Transcripción de audio a subtítulos con marcas de tiempo.

Groq y OpenAI usan el mismo formato de API (compatible con OpenAI), así que
cambiar de proveedor es cambiar una variable de entorno, no reescribir código.
OJO: OpenAI retira whisper-1 el 26-feb-2027 y su reemplazo (gpt-transcribe) no
entrega marcas de tiempo; por eso el proveedor por defecto es Groq.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.media import get_duration_seconds

MAX_AUDIO_BYTES = 24 * 1024 * 1024  # los proveedores aceptan ~25 MB


class TranscriptionError(Exception):
    """Falló la transcripción; el mensaje está pensado para el usuario."""


class TranscriptionConfigError(TranscriptionError):
    """Falta configurar el proveedor (por ejemplo, la clave de API)."""


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, language: str | None) -> list[Segment]: ...


@dataclass(frozen=True)
class Provider:
    base_url: str
    default_model: str
    key_env: str


PROVIDERS = {
    "groq": Provider("https://api.groq.com/openai/v1", "whisper-large-v3-turbo", "GROQ_API_KEY"),
    "openai": Provider("https://api.openai.com/v1", "whisper-1", "OPENAI_API_KEY"),
}


class HttpWhisperTranscriber:
    """Cliente para cualquier API de transcripción compatible con OpenAI."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0))

    def transcribe(self, audio_path: Path, language: str | None) -> list[Segment]:
        audio_path = Path(audio_path)
        if audio_path.stat().st_size > MAX_AUDIO_BYTES:
            raise TranscriptionError("El audio es demasiado grande para el servicio de transcripción.")

        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if language:
            data["language"] = language

        try:
            with open(audio_path, "rb") as f:
                response = self.client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=data,
                    files={"file": (audio_path.name, f, "audio/mpeg")},
                )
        except httpx.HTTPError as exc:
            raise TranscriptionError(
                "No pudimos conectar con el servicio de transcripción. Intenta de nuevo."
            ) from exc

        if response.status_code in (401, 403):
            raise TranscriptionError("La clave del servicio de transcripción no es válida.")
        if response.status_code == 413:
            raise TranscriptionError("El audio es demasiado grande para el servicio de transcripción.")
        if response.status_code == 429:
            raise TranscriptionError(
                "El servicio de transcripción alcanzó su límite. Espera un minuto e intenta de nuevo."
            )
        if response.status_code >= 400:
            raise TranscriptionError("El servicio de transcripción respondió con un error.")

        try:
            raw_segments = response.json().get("segments") or []
        except (ValueError, AttributeError) as exc:
            raise TranscriptionError("Respuesta inesperada del servicio de transcripción.") from exc

        segments = []
        for item in raw_segments:
            try:
                text = str(item["text"]).strip()
                start, end = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if text and end > start >= 0:
                segments.append(Segment(round(start, 2), round(end, 2), text))

        if not segments:
            raise TranscriptionError("No detectamos voz en el video.")
        return segments


class FakeTranscriber:
    """Subtítulos de mentira para probar la pantalla sin llamar a ningún servicio."""

    def transcribe(self, audio_path: Path, language: str | None) -> list[Segment]:
        duration = get_duration_seconds(str(audio_path))
        segments = []
        for i, start in enumerate(range(0, int(duration), 4)):
            end = min(start + 4, duration)
            if end > start:
                segments.append(Segment(float(start), round(end, 2), f"Subtítulo de prueba {i + 1}"))
        return segments


def get_transcriber() -> Transcriber:
    if os.environ.get("VIREVO_FAKE_TRANSCRIBER", "").lower() in ("1", "true", "si", "yes"):
        return FakeTranscriber()

    name = (os.environ.get("VIREVO_STT_PROVIDER") or "groq").lower()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise TranscriptionConfigError(f"Proveedor de transcripción desconocido: {name}.")
    api_key = os.environ.get(provider.key_env)
    if not api_key:
        raise TranscriptionConfigError(f"Falta configurar {provider.key_env} en el servidor.")
    model = os.environ.get("VIREVO_STT_MODEL") or provider.default_model
    return HttpWhisperTranscriber(provider.base_url, api_key, model)
