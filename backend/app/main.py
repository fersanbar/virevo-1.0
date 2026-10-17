import json
import logging
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv



load_dotenv()  # lee virevo-backend/.env antes de importar el resto

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware

from app.ad_rules import MAX_FREE_SECONDS, calculate_ad_plan  # noqa: E402
from app.audio import AudioExtractionError, extract_audio  # noqa: E402
from app.export import ExportError, burn_subtitles  # noqa: E402
from app.limits import check_transcription_allowed, check_upload_allowed, client_ip  # noqa: E402
from app.media import VideoInvalidoError, get_duration_seconds  # noqa: E402
from app.subtitles import build_srt  # noqa: E402
from app.store import (  # noqa: E402
    AdFlowError,
    Session,
    SessionExpiredError,
    SessionNotFoundError,
    SessionStore,
    TranscriptStateError,
)
from app.transcription import (  # noqa: E402
    TranscriptionConfigError,
    TranscriptionError,
    Transcriber,
    get_transcriber,
)

logger = logging.getLogger("virevo")

app = FastAPI()

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

DATA_DIR = Path(os.environ.get("VIREVO_DATA") or "data")
UPLOADS_DIR = DATA_DIR / "uploads"
store = SessionStore(DATA_DIR / "virevo.db")
store.fail_interrupted()

PRODUCTION = (os.environ.get("VIREVO_ENV") or "").lower() == "production"

# En producción se oculta la documentación interactiva (/docs): no hace falta que sea pública.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://virevo-v10.vercel.app",
        "https://virevo-1-0-sand.vercel.app",
    ],
    allow_origin_regex=r"https://virevo-v10-[a-z0-9-]+-virevo2\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/salud")
def salud():
    return {"ok": True}


# --- Errores del flujo -> respuestas con mensaje claro ----------------------

@app.exception_handler(SessionNotFoundError)
async def _session_not_found(request: Request, exc: SessionNotFoundError):
    return JSONResponse(
        {"detail": "No encontramos esta sesión. Sube el video de nuevo."}, status_code=404
    )


@app.exception_handler(SessionExpiredError)
async def _session_expired(request: Request, exc: SessionExpiredError):
    return JSONResponse({"detail": "La sesión expiró. Sube el video de nuevo."}, status_code=410)


@app.exception_handler(AdFlowError)
async def _ad_flow(request: Request, exc: AdFlowError):
    return JSONResponse(
        {"detail": str(exc), "seconds_left": round(exc.seconds_left, 1)}, status_code=409
    )


@app.exception_handler(TranscriptStateError)
async def _transcript_state(request: Request, exc: TranscriptStateError):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(TranscriptionConfigError)
async def _transcription_config(request: Request, exc: TranscriptionConfigError):
    logger.error("Transcripción sin configurar: %s", exc)
    return JSONResponse({"detail": str(exc)}, status_code=503)


def _state(session: Session) -> dict:
    in_progress = session.ad_started_at is not None
    left = None
    if in_progress:
        left = max(0.0, session.ad_started_at + session.seconds_per_ad - store.clock())
    return {
        "ads_required": session.ads_required,
        "ads_completed": session.ads_completed,
        "seconds_per_ad": session.seconds_per_ad,
        "unlocked": session.unlocked,
        "ad_in_progress": in_progress,
        "ad_seconds_left": None if left is None else round(left, 1),
    }


def _transcript_payload(session: Session) -> dict:
    done = session.transcript_status == "done" and session.transcript_json
    return {
        "status": session.transcript_status,
        "message": session.transcript_error,
        "segments": json.loads(session.transcript_json) if done else None,
    }


def _require_unlocked(session_id: str) -> Session:
    session = store.get(session_id)
    if not session.unlocked:
        # Esta es la puerta real: sin todos los anuncios, no hay subtítulos.
        raise HTTPException(403, "Primero debes ver todos los anuncios.")
    return session


# --- Módulo 1: analizar el video -------------------------------------------

@app.post("/api/videos/analizar")
async def analizar_video(request: Request, file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Formato no soportado. Usa MP4, MOV, MKV, WEBM o AVI.")
    check_upload_allowed(store, client_ip(request))

    # Limpieza: sesiones vencidas y sus videos.
    for old_path in store.purge_expired():
        Path(old_path).unlink(missing_ok=True)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    video_path = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"

    try:
        size = 0
        with open(video_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "El archivo supera los 500 MB.")
                out.write(chunk)
        duration = get_duration_seconds(str(video_path))
    except VideoInvalidoError as exc:
        video_path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        video_path.unlink(missing_ok=True)
        raise

    plan = calculate_ad_plan(duration)
    session_id = None
    if plan.allowed:
        session_id = store.create(
            str(video_path), duration, plan.ads_required, plan.seconds_per_ad
        ).id
    else:
        video_path.unlink(missing_ok=True)

    return {
        "session_id": session_id,
        "duration_seconds": round(duration, 1),
        "max_free_seconds": MAX_FREE_SECONDS,
        **asdict(plan),
    }


# --- Módulo 2: anuncios validados por el servidor ---------------------------

@app.get("/api/sesiones/{session_id}")
def estado_sesion(session_id: str):
    return _state(store.get(session_id))


@app.post("/api/sesiones/{session_id}/anuncios/iniciar")
def iniciar_anuncio(session_id: str):
    return _state(store.start_ad(session_id))


@app.post("/api/sesiones/{session_id}/anuncios/completar")
def completar_anuncio(session_id: str):
    return _state(store.complete_ad(session_id))


# --- Módulo 3: transcripción y edición de subtítulos ------------------------

class TranscribeRequest(BaseModel):
    idioma: Literal["es", "en"] | None = None  # None = detectar automáticamente


class SegmentIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=500)


class SaveRequest(BaseModel):
    segments: list[SegmentIn] = Field(max_length=2000)


def _run_transcription(session_id: str, video_path: str, language: str | None,
                       transcriber: Transcriber) -> None:
    audio_path = Path(video_path).with_suffix(".mp3")
    try:
        extract_audio(video_path, audio_path)
        segments = transcriber.transcribe(audio_path, language)
        store.finish_transcript(session_id, [asdict(s) for s in segments])
    except (TranscriptionError, AudioExtractionError) as exc:
        store.fail_transcript(session_id, str(exc))
    except Exception:
        logger.exception("Falló la transcripción de la sesión %s", session_id)
        store.fail_transcript(session_id, "No pudimos generar los subtítulos. Intenta de nuevo.")
    finally:
        audio_path.unlink(missing_ok=True)


@app.post("/api/sesiones/{session_id}/transcribir")
def transcribir(session_id: str, body: TranscribeRequest, background_tasks: BackgroundTasks,
                request: Request):
    session = _require_unlocked(session_id)
    if session.transcript_status in ("processing", "done"):
        return _transcript_payload(session)  # idempotente: no se vuelve a cobrar

    transcriber = get_transcriber()  # si falta configurar, responde 503 antes de marcar nada
    ip = client_ip(request)
    check_transcription_allowed(store, ip)  # 429 si se pasó de los límites diarios
    if store.begin_transcript(session_id):
        store.record_event("transcription", ip)  # solo cuenta si de verdad arranca
        background_tasks.add_task(
            _run_transcription, session_id, session.video_path, body.idioma, transcriber
        )
    return _transcript_payload(store.get(session_id))


@app.get("/api/sesiones/{session_id}/subtitulos")
def subtitulos(session_id: str):
    _require_unlocked(session_id)
    return _transcript_payload(store.get(session_id))


@app.put("/api/sesiones/{session_id}/subtitulos")
def guardar_subtitulos(session_id: str, body: SaveRequest):
    session = _require_unlocked(session_id)
    cleaned = []
    for seg in sorted(body.segments, key=lambda s: s.start):
        text = seg.text.strip()
        if not text:
            continue  # un subtítulo vacío equivale a borrarlo
        if seg.end <= seg.start:
            raise HTTPException(422, "Hay un subtítulo cuyo final es anterior a su inicio.")
        end = min(seg.end, session.duration_seconds)
        if seg.start >= end:
            continue  # empieza después de que termina el video
        cleaned.append({"start": round(seg.start, 2), "end": round(end, 2), "text": text})
    store.save_segments(session_id, cleaned)
    return _transcript_payload(store.get(session_id))


# --- Módulo 4: video con subtítulos incrustados y descargas ----------------

def _export_payload(session: Session) -> dict:
    return {"status": session.export_status, "message": session.export_error}


def _run_export(session_id: str, video_path: str, segments: list[dict]) -> None:
    out_path = Path(video_path).with_name(Path(video_path).stem + ".subtitulado.mp4")
    try:
        burn_subtitles(video_path, segments, out_path)
        store.finish_export(session_id, str(out_path))
    except ExportError as exc:
        store.fail_export(session_id, str(exc))
    except Exception:
        logger.exception("Falló la exportación de la sesión %s", session_id)
        store.fail_export(session_id, "No pudimos crear el video con subtítulos. Intenta de nuevo.")


@app.post("/api/sesiones/{session_id}/exportar")
def exportar(session_id: str, background_tasks: BackgroundTasks):
    session = _require_unlocked(session_id)
    if session.transcript_status != "done" or not session.transcript_json:
        raise TranscriptStateError("Primero genera los subtítulos.")
    segments = json.loads(session.transcript_json)
    if not segments:
        raise HTTPException(422, "No hay subtítulos para incrustar en el video.")
    if store.begin_export(session_id):
        background_tasks.add_task(_run_export, session_id, session.video_path, segments)
    return _export_payload(store.get(session_id))


@app.get("/api/sesiones/{session_id}/exportacion")
def estado_exportacion(session_id: str):
    _require_unlocked(session_id)
    return _export_payload(store.get(session_id))


@app.get("/api/sesiones/{session_id}/descargar/video")
def descargar_video(session_id: str):
    session = _require_unlocked(session_id)
    if (session.export_status != "done" or not session.export_path
            or not Path(session.export_path).exists()):
        raise HTTPException(409, "Primero crea el video con subtítulos.")
    return FileResponse(session.export_path, media_type="video/mp4",
                        filename="video-con-subtitulos.mp4")


@app.get("/api/sesiones/{session_id}/descargar/srt")
def descargar_srt(session_id: str):
    session = _require_unlocked(session_id)
    if session.transcript_status != "done" or not session.transcript_json:
        raise HTTPException(409, "Primero genera los subtítulos.")
    content = build_srt(json.loads(session.transcript_json))
    return Response(
        content,
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="subtitulos.srt"'},
    )
