"""Límites de uso para que nadie pueda gastar tu saldo de transcripción ni llenarte el disco.

Todos se configuran en el .env; el valor 0 desactiva el límite (útil mientras desarrollas).
Las ventanas son móviles (últimas 1 h / últimas 24 h), no días de calendario.
"""
import os

from fastapi import HTTPException, Request

HOUR = 3600
DAY = 24 * HOUR


def _limit(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def client_ip(request: Request) -> str:
    """IP del visitante. Solo se confía en X-Forwarded-For si el servidor está detrás de
    tu propio proxy (VIREVO_TRUST_PROXY=1); si no, cualquiera podría falsificarla."""
    if (os.environ.get("VIREVO_TRUST_PROXY") or "").lower() in ("1", "true", "si", "yes"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def check_upload_allowed(store, ip: str) -> None:
    limit = _limit("VIREVO_UPLOADS_PER_HOUR_PER_IP", 10)
    if limit > 0 and store.count_events("upload", HOUR, ip) >= limit:
        raise HTTPException(429, "Subiste muchos videos en poco tiempo. Intenta de nuevo en una hora.")
    store.record_event("upload", ip)


def check_transcription_allowed(store, ip: str) -> None:
    total = _limit("VIREVO_TRANSCRIPTIONS_PER_DAY", 300)
    per_ip = _limit("VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", 15)
    if total > 0 and store.count_events("transcription", DAY) >= total:
        raise HTTPException(429, "Se alcanzó el límite diario de transcripciones del servicio. Intenta mañana.")
    if per_ip > 0 and store.count_events("transcription", DAY, ip) >= per_ip:
        raise HTTPException(429, "Alcanzaste tu límite de transcripciones por hoy. Intenta mañana.")
