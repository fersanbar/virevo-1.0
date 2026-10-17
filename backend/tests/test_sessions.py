import pytest

from app.store import (
    SESSION_TTL_SECONDS,
    AdFlowError,
    SessionExpiredError,
    SessionStore,
)


@pytest.fixture
def store(tmp_path, clock):
    return SessionStore(tmp_path / "s.db", clock=clock)


def test_tres_anuncios_en_orden(store, clock):
    s = store.create("v.mp4", 700, ads_required=3, seconds_per_ad=20)
    for i in range(3):
        store.start_ad(s.id)
        with pytest.raises(AdFlowError):
            store.complete_ad(s.id)                 # no se puede saltar
        clock.advance(20)
        s = store.complete_ad(s.id)
        assert s.ads_completed == i + 1
    assert s.unlocked


def test_el_error_dice_cuanto_falta(store, clock):
    s = store.create("v.mp4", 60, 1, 20)
    store.start_ad(s.id)
    clock.advance(5)
    with pytest.raises(AdFlowError) as exc:
        store.complete_ad(s.id)
    assert 14 < exc.value.seconds_left < 16


def test_iniciar_dos_veces_no_reinicia_el_reloj(store, clock):
    s = store.create("v.mp4", 60, 1, 20)
    first = store.start_ad(s.id)
    clock.advance(10)
    second = store.start_ad(s.id)
    assert second.ad_started_at == first.ad_started_at


def test_no_se_puede_completar_sin_iniciar(store):
    s = store.create("v.mp4", 60, 1, 20)
    with pytest.raises(AdFlowError):
        store.complete_ad(s.id)


def test_no_se_puede_pasar_de_los_anuncios_requeridos(store, clock):
    s = store.create("v.mp4", 60, 1, 20)
    store.start_ad(s.id)
    clock.advance(20)
    store.complete_ad(s.id)
    with pytest.raises(AdFlowError):
        store.start_ad(s.id)
    with pytest.raises(AdFlowError):
        store.complete_ad(s.id)


def test_la_sesion_expira(store, clock):
    s = store.create("v.mp4", 60, 1, 20)
    clock.advance(SESSION_TTL_SECONDS + 1)
    with pytest.raises(SessionExpiredError):
        store.get(s.id)


def test_purge_devuelve_los_videos_vencidos(store, clock):
    old = store.create("viejo.mp4", 60, 1, 20)
    clock.advance(SESSION_TTL_SECONDS + 1)
    new = store.create("nuevo.mp4", 60, 1, 20)
    assert store.purge_expired() == ["viejo.mp4"]
    assert store.get(new.id).video_path == "nuevo.mp4"
    assert old.id != new.id


# --- Módulo 3: estado de la transcripción -----------------------------------

import sqlite3  # noqa: E402

from app.store import TranscriptStateError  # noqa: E402


def _unlocked(store, clock):
    s = store.create("v.mp4", 60, 1, 20)
    store.start_ad(s.id)
    clock.advance(20)
    return store.complete_ad(s.id)


def test_begin_transcript_exige_anuncios_completos(store):
    s = store.create("v.mp4", 60, 1, 20)
    assert store.begin_transcript(s.id) is False
    assert store.get(s.id).transcript_status == "none"


def test_solo_una_peticion_arranca_la_transcripcion(store, clock):
    s = _unlocked(store, clock)
    assert store.begin_transcript(s.id) is True
    assert store.begin_transcript(s.id) is False     # la segunda no cobra otra vez


def test_ciclo_de_estados(store, clock):
    s = _unlocked(store, clock)
    store.begin_transcript(s.id)
    store.fail_transcript(s.id, "boom")
    assert store.get(s.id).transcript_status == "error"
    assert store.begin_transcript(s.id) is True      # tras un error se puede reintentar
    store.finish_transcript(s.id, [{"start": 0, "end": 1, "text": "hola"}])
    done = store.get(s.id)
    assert done.transcript_status == "done" and done.transcript_error is None
    assert store.begin_transcript(s.id) is False     # ya terminó


def test_guardar_exige_transcripcion_terminada(store, clock):
    s = _unlocked(store, clock)
    with pytest.raises(TranscriptStateError):
        store.save_segments(s.id, [])


def test_lo_interrumpido_queda_como_error(store, clock):
    s = _unlocked(store, clock)
    store.begin_transcript(s.id)
    store.fail_interrupted()
    assert store.get(s.id).transcript_status == "error"


def test_migra_una_base_de_datos_anterior_al_modulo_3(tmp_path, clock):
    db = tmp_path / "viejo.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, video_path TEXT NOT NULL, "
        "duration_seconds REAL NOT NULL, ads_required INTEGER NOT NULL, "
        "seconds_per_ad INTEGER NOT NULL, ads_completed INTEGER NOT NULL DEFAULT 0, "
        "ad_started_at REAL, created_at REAL NOT NULL)"
    )
    conn.execute("INSERT INTO sessions VALUES ('abc', 'v.mp4', 60, 1, 20, 0, NULL, ?)", (clock(),))
    conn.commit()
    conn.close()

    store = SessionStore(db, clock=clock)            # debe agregar las columnas nuevas
    session = store.get("abc")
    assert session.transcript_status == "none" and session.transcript_json is None


# --- Módulo 4: exportación ---------------------------------------------------

def _transcribed(store, clock):
    s = _unlocked(store, clock)
    store.begin_transcript(s.id)
    store.finish_transcript(s.id, [{"start": 0, "end": 1, "text": "hola"}])
    return s


def test_exportar_exige_subtitulos_listos(store, clock):
    s = _unlocked(store, clock)
    assert store.begin_export(s.id) is False


def test_solo_una_exportacion_a_la_vez(store, clock):
    s = _transcribed(store, clock)
    assert store.begin_export(s.id) is True
    assert store.begin_export(s.id) is False
    store.finish_export(s.id, "out.mp4")
    done = store.get(s.id)
    assert done.export_status == "done" and done.export_path == "out.mp4"
    assert store.begin_export(s.id) is True        # se puede volver a exportar


def test_no_se_guarda_mientras_se_exporta(store, clock):
    s = _transcribed(store, clock)
    store.begin_export(s.id)
    with pytest.raises(TranscriptStateError) as exc:
        store.save_segments(s.id, [])
    assert "exportación" in str(exc.value)


def test_guardar_invalida_el_video_exportado(store, clock):
    s = _transcribed(store, clock)
    store.begin_export(s.id)
    store.finish_export(s.id, "out.mp4")
    store.save_segments(s.id, [{"start": 0, "end": 1, "text": "cambiado"}])
    assert store.get(s.id).export_status == "none"


def test_purge_incluye_los_videos_exportados(store, clock):
    s = _transcribed(store, clock)
    store.begin_export(s.id)
    store.finish_export(s.id, "out.mp4")
    clock.advance(SESSION_TTL_SECONDS + 1)
    assert store.purge_expired() == ["v.mp4", "out.mp4"]


def test_exportacion_interrumpida_queda_como_error(store, clock):
    s = _transcribed(store, clock)
    store.begin_export(s.id)
    store.fail_interrupted()
    assert store.get(s.id).export_status == "error"


# --- Límites de uso: eventos -------------------------------------------------

def test_cuenta_eventos_por_tipo_ip_y_ventana(store, clock):
    store.record_event("upload", "1.1.1.1")
    store.record_event("upload", "2.2.2.2")
    store.record_event("transcription", "1.1.1.1")
    assert store.count_events("upload", 3600) == 2
    assert store.count_events("upload", 3600, ip="1.1.1.1") == 1
    assert store.count_events("transcription", 3600) == 1
    clock.advance(1800)
    store.record_event("upload", "1.1.1.1")
    assert store.count_events("upload", 3600) == 3
    clock.advance(1801)                                  # los dos primeros salen de la ventana
    assert store.count_events("upload", 3600) == 1


def test_purge_borra_eventos_de_hace_mas_de_dos_dias(store, clock):
    store.record_event("upload", "1.1.1.1")
    clock.advance(2 * 24 * 3600 + 1)
    store.purge_expired()
    assert store.count_events("upload", 10 * 24 * 3600) == 0
