def upload(client, path, name="demo.mp4"):
    with open(path, "rb") as f:
        return client.post("/videos/analizar", files={"file": (name, f, "video/mp4")})


def test_analiza_video_de_7_segundos(client, make_video):
    r = upload(client, make_video(7))
    assert r.status_code == 200
    body = r.json()
    assert round(body["duration_seconds"]) == 7
    assert body["allowed"] and body["ads_required"] == 1
    assert body["max_free_seconds"] == 900
    assert body["session_id"]


def test_video_muy_largo_no_crea_sesion_ni_guarda_archivo(client, make_video, tmp_path):
    body = upload(client, make_video(1000)).json()
    assert not body["allowed"] and body["session_id"] is None
    assert not list((tmp_path / "uploads").glob("*"))


def test_rechaza_archivo_que_no_es_video(client, tmp_path):
    r = client.post("/videos/analizar", files={"file": ("fake.mp4", b"hola", "video/mp4")})
    assert r.status_code == 400
    assert not list((tmp_path / "uploads").glob("*"))


def test_rechaza_extension_no_soportada(client):
    r = client.post("/videos/analizar", files={"file": ("doc.pdf", b"x", "application/pdf")})
    assert r.status_code == 400


def test_flujo_completo_de_anuncio(client, make_video, clock):
    body = upload(client, make_video(7)).json()
    sid, secs = body["session_id"], body["seconds_per_ad"]
    subs = f"/sesiones/{sid}/subtitulos"
    start = f"/sesiones/{sid}/anuncios/iniciar"
    done = f"/sesiones/{sid}/anuncios/completar"

    assert client.get(subs).status_code == 403          # sin anuncio, no hay subtítulos

    r = client.post(start)
    assert r.status_code == 200 and r.json()["ad_in_progress"]

    early = client.post(done)                           # intento de saltarse el anuncio
    assert early.status_code == 409 and early.json()["seconds_left"] > 0
    assert client.get(subs).status_code == 403

    clock.advance(secs - 2)                             # todavía faltan 2 s
    assert client.post(done).status_code == 409

    clock.advance(2)
    r = client.post(done)
    assert r.status_code == 200 and r.json()["unlocked"]
    assert client.get(subs).status_code == 200


def test_completar_sin_iniciar_falla(client, make_video):
    sid = upload(client, make_video(7)).json()["session_id"]
    assert client.post(f"/sesiones/{sid}/anuncios/completar").status_code == 409


def test_recargar_no_reinicia_el_reloj(client, make_video, clock):
    sid = upload(client, make_video(7)).json()["session_id"]
    client.post(f"/sesiones/{sid}/anuncios/iniciar")
    clock.advance(10)
    r = client.post(f"/sesiones/{sid}/anuncios/iniciar")
    assert r.json()["ad_seconds_left"] < 15             # siguió corriendo, no volvió a 20


def test_sesion_inexistente_da_404(client):
    assert client.get("/sesiones/no-existe").status_code == 404
    assert client.get("/sesiones/no-existe/subtitulos").status_code == 404


# --- Módulo 3: transcripción -------------------------------------------------

import pytest  # noqa: E402

from app import main  # noqa: E402
from app.transcription import (  # noqa: E402
    FakeTranscriber,
    Segment,
    TranscriptionConfigError,
    TranscriptionError,
)


def unlock(client, clock, sid, secs):
    client.post(f"/sesiones/{sid}/anuncios/iniciar")
    clock.advance(secs)
    assert client.post(f"/sesiones/{sid}/anuncios/completar").json()["unlocked"]


@pytest.fixture
def unlocked(client, make_video, clock):
    """Sesión con el anuncio ya visto (video de 7 s con audio)."""
    body = upload(client, make_video(7)).json()
    unlock(client, clock, body["session_id"], body["seconds_per_ad"])
    return body["session_id"]


def test_no_se_puede_transcribir_sin_ver_anuncios(client, make_video):
    sid = upload(client, make_video(7)).json()["session_id"]
    r = client.post(f"/sesiones/{sid}/transcribir", json={"idioma": "es"})
    assert r.status_code == 403
    assert client.put(f"/sesiones/{sid}/subtitulos", json={"segments": []}).status_code == 403


def test_transcribe_y_devuelve_segmentos(client, unlocked):
    r = client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    assert r.status_code == 200 and r.json()["status"] == "processing"

    body = client.get(f"/sesiones/{unlocked}/subtitulos").json()
    assert body["status"] == "done"
    assert len(body["segments"]) == 2           # 7 s en bloques de 4 s
    assert body["segments"][0]["text"] == "Subtítulo de prueba 1"


def test_idioma_invalido_da_422(client, unlocked):
    r = client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "klingon"})
    assert r.status_code == 422


def test_no_se_cobra_dos_veces(client, unlocked, monkeypatch):
    calls = []

    class Counting(FakeTranscriber):
        def transcribe(self, audio_path, language):
            calls.append(language)
            return super().transcribe(audio_path, language)

    monkeypatch.setattr(main, "get_transcriber", lambda: Counting())
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    assert calls == ["es"]


def test_error_del_proveedor_permite_reintentar(client, unlocked, monkeypatch):
    class Failing:
        def transcribe(self, audio_path, language):
            raise TranscriptionError("El servicio de transcripción alcanzó su límite.")

    monkeypatch.setattr(main, "get_transcriber", lambda: Failing())
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": None})
    body = client.get(f"/sesiones/{unlocked}/subtitulos").json()
    assert body["status"] == "error" and "límite" in body["message"]

    monkeypatch.setattr(main, "get_transcriber", lambda: FakeTranscriber())  # ya funciona
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": None})
    assert client.get(f"/sesiones/{unlocked}/subtitulos").json()["status"] == "done"


def test_falla_inesperada_no_filtra_detalles(client, unlocked, monkeypatch):
    class Broken:
        def transcribe(self, audio_path, language):
            raise RuntimeError("secreto interno")

    monkeypatch.setattr(main, "get_transcriber", lambda: Broken())
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": None})
    body = client.get(f"/sesiones/{unlocked}/subtitulos").json()
    assert body["status"] == "error" and "secreto" not in body["message"]


def test_sin_configurar_da_503_y_no_marca_nada(client, unlocked, monkeypatch):
    def not_configured():
        raise TranscriptionConfigError("Falta configurar GROQ_API_KEY en el servidor.")

    monkeypatch.setattr(main, "get_transcriber", not_configured)
    r = client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]
    assert client.get(f"/sesiones/{unlocked}/subtitulos").json()["status"] == "none"


def test_video_sin_audio_da_mensaje_claro(client, make_video, clock):
    body = upload(client, make_video(7, audio=False)).json()
    sid = body["session_id"]
    unlock(client, clock, sid, body["seconds_per_ad"])
    client.post(f"/sesiones/{sid}/transcribir", json={"idioma": "es"})
    result = client.get(f"/sesiones/{sid}/subtitulos").json()
    assert result["status"] == "error" and "no tiene pista de audio" in result["message"]


def test_el_audio_temporal_se_borra(client, unlocked, tmp_path):
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    assert not list((tmp_path / "uploads").glob("*.mp3"))


def test_guardar_ediciones(client, unlocked):
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    segs = client.get(f"/sesiones/{unlocked}/subtitulos").json()["segments"]

    edited = [{**segs[1], "text": "  Hola mundo  "}, {**segs[0], "text": "   "}]  # desordenado y uno vacío
    r = client.put(f"/sesiones/{unlocked}/subtitulos", json={"segments": edited})
    assert r.status_code == 200
    saved = client.get(f"/sesiones/{unlocked}/subtitulos").json()["segments"]
    assert [s["text"] for s in saved] == ["Hola mundo"]


def test_guardar_recorta_tiempos_pasados_del_video(client, unlocked):
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    r = client.put(f"/sesiones/{unlocked}/subtitulos",
                   json={"segments": [{"start": 4, "end": 60, "text": "final"}]})
    assert r.json()["segments"][0]["end"] <= 7.1


def test_guardar_rechaza_tiempos_invertidos(client, unlocked):
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    r = client.put(f"/sesiones/{unlocked}/subtitulos",
                   json={"segments": [{"start": 5, "end": 2, "text": "x"}]})
    assert r.status_code == 422


def test_no_se_guarda_antes_de_transcribir(client, unlocked):
    r = client.put(f"/sesiones/{unlocked}/subtitulos",
                   json={"segments": [{"start": 0, "end": 2, "text": "x"}]})
    assert r.status_code == 409


def test_segment_es_inmutable():
    assert Segment(0, 1, "a") == Segment(0, 1, "a")


# --- Módulo 4: exportar y descargar -----------------------------------------

import subprocess  # noqa: E402

from app.export import burn_subtitles as real_burn  # noqa: E402


@pytest.fixture
def transcribed(client, unlocked):
    client.post(f"/sesiones/{unlocked}/transcribir", json={"idioma": "es"})
    return unlocked


def test_exportar_exige_subtitulos(client, unlocked):
    r = client.post(f"/sesiones/{unlocked}/exportar")
    assert r.status_code == 409 and "genera los subtítulos" in r.json()["detail"]


def test_exportar_exige_anuncios(client, make_video):
    sid = upload(client, make_video(7)).json()["session_id"]
    assert client.post(f"/sesiones/{sid}/exportar").status_code == 403
    assert client.get(f"/sesiones/{sid}/descargar/srt").status_code == 403
    assert client.get(f"/sesiones/{sid}/descargar/video").status_code == 403


def test_flujo_de_exportacion_y_descarga(client, transcribed, tmp_path):
    assert client.get(f"/sesiones/{transcribed}/descargar/video").status_code == 409  # aún no existe

    r = client.post(f"/sesiones/{transcribed}/exportar")
    assert r.status_code == 200
    state = client.get(f"/sesiones/{transcribed}/exportacion").json()
    assert state["status"] == "done", state

    r = client.get(f"/sesiones/{transcribed}/descargar/video")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert "video-con-subtitulos.mp4" in r.headers["content-disposition"]
    out = tmp_path / "descargado.mp4"
    out.write_bytes(r.content)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True).stdout)
    assert abs(duration - 7) < 1
    assert not list((tmp_path / "uploads").glob("*.ass"))


def test_descargar_srt(client, transcribed):
    r = client.get(f"/sesiones/{transcribed}/descargar/srt")
    assert r.status_code == 200
    assert "subtitulos.srt" in r.headers["content-disposition"]
    assert r.text.startswith("1\n00:00:00,000 --> 00:00:04,000\nSubtítulo de prueba 1")


def test_srt_antes_de_transcribir(client, unlocked):
    assert client.get(f"/sesiones/{unlocked}/descargar/srt").status_code == 409


def test_editar_invalida_el_video_exportado(client, transcribed):
    client.post(f"/sesiones/{transcribed}/exportar")
    segs = client.get(f"/sesiones/{transcribed}/subtitulos").json()["segments"]
    client.put(f"/sesiones/{transcribed}/subtitulos", json={"segments": segs})
    assert client.get(f"/sesiones/{transcribed}/exportacion").json()["status"] == "none"
    assert client.get(f"/sesiones/{transcribed}/descargar/video").status_code == 409


def test_exportar_con_error_permite_reintentar(client, transcribed, monkeypatch):
    def broken(*args, **kwargs):
        raise main.ExportError("Tu FFmpeg no incluye soporte de subtítulos (libass).")

    monkeypatch.setattr(main, "burn_subtitles", broken)
    client.post(f"/sesiones/{transcribed}/exportar")
    state = client.get(f"/sesiones/{transcribed}/exportacion").json()
    assert state["status"] == "error" and "libass" in state["message"]

    monkeypatch.setattr(main, "burn_subtitles", real_burn)   # ya funciona
    client.post(f"/sesiones/{transcribed}/exportar")
    assert client.get(f"/sesiones/{transcribed}/exportacion").json()["status"] == "done"


def test_salud(client):
    assert client.get("/salud").json() == {"ok": True}
