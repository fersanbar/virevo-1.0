"""Sesiones de anuncios guardadas en SQLite (viene con Python, no instalas nada).

Idea clave: TODOS los tiempos los mide el servidor. El navegador nunca manda
una hora ni dice "ya pasaron 20 segundos"; solo avisa "inicié" y "terminé", y
el servidor compara con su propio reloj.
"""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SESSION_TTL_SECONDS = 2 * 60 * 60   # una sesión dura 2 horas
CLOCK_TOLERANCE_SECONDS = 0.5       # margen por latencia de red


class SessionNotFoundError(Exception):
    pass


class SessionExpiredError(Exception):
    pass


class TranscriptStateError(Exception):
    """La acción no corresponde al estado actual de la transcripción."""


class AdFlowError(Exception):
    """El usuario intentó algo que el flujo de anuncios no permite."""

    def __init__(self, message: str, seconds_left: float = 0.0):
        super().__init__(message)
        self.seconds_left = seconds_left


@dataclass(frozen=True)
class Session:
    id: str
    video_path: str
    duration_seconds: float
    ads_required: int
    seconds_per_ad: int
    ads_completed: int
    ad_started_at: float | None
    created_at: float
    transcript_status: str = "none"       # none | processing | done | error
    transcript_json: str | None = None    # lista de subtítulos (JSON)
    transcript_error: str | None = None
    export_status: str = "none"           # none | processing | done | error
    export_error: str | None = None
    export_path: str | None = None        # video con subtítulos incrustados

    @property
    def unlocked(self) -> bool:
        return self.ads_completed >= self.ads_required


class SessionStore:
    def __init__(self, db_path: Path, clock: Callable[[], float] = time.time):
        self.db_path = Path(db_path)
        self.clock = clock
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    video_path TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    ads_required INTEGER NOT NULL,
                    seconds_per_ad INTEGER NOT NULL,
                    ads_completed INTEGER NOT NULL DEFAULT 0,
                    ad_started_at REAL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage ON usage_events (kind, created_at)"
            )
            # Migración: bases creadas antes del Módulo 3 no tienen estas columnas.
            existing = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
            for name, ddl in (
                ("transcript_status", "TEXT NOT NULL DEFAULT 'none'"),
                ("transcript_json", "TEXT"),
                ("transcript_error", "TEXT"),
                ("export_status", "TEXT NOT NULL DEFAULT 'none'"),
                ("export_error", "TEXT"),
                ("export_path", "TEXT"),
            ):
                if name not in existing:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {ddl}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create(self, video_path: str, duration: float, ads_required: int,
               seconds_per_ad: int) -> Session:
        session_id = secrets.token_urlsafe(16)  # imposible de adivinar
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, video_path, duration_seconds, ads_required,"
                " seconds_per_ad, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, video_path, duration, ads_required, seconds_per_ad, self.clock()),
            )
        return self.get(session_id)

    def get(self, session_id: str) -> Session:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        session = Session(**dict(row))
        if self.clock() - session.created_at > SESSION_TTL_SECONDS:
            raise SessionExpiredError(session_id)
        return session

    def start_ad(self, session_id: str) -> Session:
        """Anota la hora de inicio del siguiente anuncio.

        Es idempotente: si ya hay un anuncio en curso (por ejemplo, el usuario
        recargó la página) NO se reinicia el reloj, así no se puede "resetear"
        ni alargar o acortar la espera.
        """
        session = self.get(session_id)
        if session.unlocked:
            raise AdFlowError("Ya viste todos los anuncios.")
        if session.ad_started_at is None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET ad_started_at = ? "
                    "WHERE id = ? AND ad_started_at IS NULL",
                    (self.clock(), session_id),
                )
        return self.get(session_id)

    def complete_ad(self, session_id: str) -> Session:
        """Cuenta el anuncio como visto solo si el servidor midió el tiempo completo."""
        now = self.clock()
        with self._connect() as conn:
            # Un solo UPDATE atómico: revisa las condiciones y avanza a la vez.
            changed = conn.execute(
                "UPDATE sessions SET ads_completed = ads_completed + 1, ad_started_at = NULL "
                "WHERE id = ? AND ad_started_at IS NOT NULL AND ads_completed < ads_required "
                "AND ? - ad_started_at >= seconds_per_ad - ?",
                (session_id, now, CLOCK_TOLERANCE_SECONDS),
            ).rowcount
        session = self.get(session_id)
        if changed:
            return session
        if session.unlocked:
            raise AdFlowError("Ya viste todos los anuncios.")
        if session.ad_started_at is None:
            raise AdFlowError("Primero inicia un anuncio.")
        left = session.ad_started_at + session.seconds_per_ad - now
        raise AdFlowError("El anuncio aún no termina.", seconds_left=max(0.0, left))

    def purge_expired(self) -> list[str]:
        """Borra sesiones vencidas y devuelve las rutas de sus archivos para eliminarlos."""
        cutoff = self.clock() - SESSION_TTL_SECONDS
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT video_path, export_path FROM sessions WHERE created_at < ?", (cutoff,)
            ).fetchall()
            conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM usage_events WHERE created_at < ?", (self.clock() - 2 * 24 * 3600,)
            )
        paths = []
        for row in rows:
            paths.append(row["video_path"])
            if row["export_path"]:
                paths.append(row["export_path"])
        return paths

    # --- Transcripción ------------------------------------------------------

    def begin_transcript(self, session_id: str) -> bool:
        """Pasa a 'processing' y devuelve True si hay que arrancar el trabajo.

        El UPDATE es atómico y exige anuncios completos: aunque lleguen dos
        peticiones a la vez, solo una arranca (y solo se paga una transcripción).
        """
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE sessions SET transcript_status = 'processing', transcript_error = NULL "
                "WHERE id = ? AND transcript_status IN ('none', 'error') "
                "AND ads_completed >= ads_required",
                (session_id,),
            ).rowcount
        return bool(changed)

    def finish_transcript(self, session_id: str, segments: list[dict]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET transcript_status = 'done', transcript_json = ?, "
                "transcript_error = NULL WHERE id = ?",
                (json.dumps(segments, ensure_ascii=False), session_id),
            )

    def fail_transcript(self, session_id: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET transcript_status = 'error', transcript_error = ? WHERE id = ?",
                (message, session_id),
            )

    def fail_interrupted(self) -> None:
        """Al arrancar el servidor: lo que quedó 'processing' se interrumpió, permite reintentar.

        Supone un solo proceso de servidor (suficiente para el MVP).
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET transcript_status = 'error', "
                "transcript_error = 'Se interrumpió la transcripción. Intenta de nuevo.' "
                "WHERE transcript_status = 'processing'"
            )
            conn.execute(
                "UPDATE sessions SET export_status = 'error', "
                "export_error = 'Se interrumpió la exportación. Intenta de nuevo.' "
                "WHERE export_status = 'processing'"
            )

    def save_segments(self, session_id: str, segments: list[dict]) -> None:
        with self._connect() as conn:
            # Guardar invalida el video exportado antes (ya no coincide con los subtítulos).
            changed = conn.execute(
                "UPDATE sessions SET transcript_json = ?, export_status = 'none', export_error = NULL "
                "WHERE id = ? AND transcript_status = 'done' AND export_status != 'processing'",
                (json.dumps(segments, ensure_ascii=False), session_id),
            ).rowcount
        if changed:
            return
        if self.get(session_id).transcript_status != "done":
            raise TranscriptStateError("Todavía no hay subtítulos para guardar.")
        raise TranscriptStateError("Espera a que termine la exportación para guardar cambios.")

    # --- Exportación (video con subtítulos incrustados) ---------------------

    def begin_export(self, session_id: str) -> bool:
        """Pasa a 'processing' y devuelve True si hay que arrancar el trabajo."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE sessions SET export_status = 'processing', export_error = NULL "
                "WHERE id = ? AND export_status != 'processing' AND transcript_status = 'done'",
                (session_id,),
            ).rowcount
        return bool(changed)

    def finish_export(self, session_id: str, path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET export_status = 'done', export_path = ?, export_error = NULL "
                "WHERE id = ?",
                (path, session_id),
            )

    def fail_export(self, session_id: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET export_status = 'error', export_error = ? WHERE id = ?",
                (message, session_id),
            )

    # --- Límites de uso ------------------------------------------------------

    def record_event(self, kind: str, ip: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_events (ip, kind, created_at) VALUES (?, ?, ?)",
                (ip, kind, self.clock()),
            )

    def count_events(self, kind: str, window_seconds: float, ip: str | None = None) -> int:
        since = self.clock() - window_seconds
        query = "SELECT COUNT(*) FROM usage_events WHERE kind = ? AND created_at >= ?"
        params: list = [kind, since]
        if ip is not None:
            query += " AND ip = ?"
            params.append(ip)
        with self._connect() as conn:
            return conn.execute(query, params).fetchone()[0]
