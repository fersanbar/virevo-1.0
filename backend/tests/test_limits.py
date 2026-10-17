import pytest

from tests.test_api import unlock, upload


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("VIREVO_UPLOADS_PER_HOUR_PER_IP", "VIREVO_TRANSCRIPTIONS_PER_DAY",
                 "VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", "VIREVO_TRUST_PROXY"):
        monkeypatch.delenv(name, raising=False)


def unlocked_session(client, make_video, clock, name="v.mp4"):
    body = upload(client, make_video(7, name=name)).json()
    unlock(client, clock, body["session_id"], body["seconds_per_ad"])
    return body["session_id"]


def transcribe(client, sid, headers=None):
    return client.post(f"/sesiones/{sid}/transcribir", json={"idioma": "es"}, headers=headers or {})


# --- Subidas por IP ----------------------------------------------------------

def test_limite_de_subidas_por_hora(client, make_video, clock, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "2")
    video = make_video(7)
    assert upload(client, video).status_code == 200
    assert upload(client, video).status_code == 200
    r = upload(client, video)
    assert r.status_code == 429 and "una hora" in r.json()["detail"]

    clock.advance(3601)                                  # pasó la hora: vuelve a permitir
    assert upload(client, video).status_code == 200


def test_un_archivo_invalido_no_gasta_cupo(client, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "1")
    for _ in range(3):
        r = client.post("/videos/analizar", files={"file": ("doc.pdf", b"x", "application/pdf")})
        assert r.status_code == 400                      # formato inválido, no 429


# --- Transcripciones ---------------------------------------------------------

def test_limite_global_diario_de_transcripciones(client, make_video, clock, monkeypatch):
    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY", "1")
    first = unlocked_session(client, make_video, clock)
    second = unlocked_session(client, make_video, clock)

    assert transcribe(client, first).status_code == 200
    r = transcribe(client, second)
    assert r.status_code == 429 and "límite diario" in r.json()["detail"]
    assert client.get(f"/sesiones/{second}/subtitulos").json()["status"] == "none"  # no se marcó nada

    clock.advance(24 * 3600 + 1)                         # pasó un día (la sesión anterior ya caducó)
    third = unlocked_session(client, make_video, clock, name="v3.mp4")
    assert transcribe(client, third).status_code == 200


def test_limite_diario_por_ip(client, make_video, clock, monkeypatch):
    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", "1")
    first = unlocked_session(client, make_video, clock)
    second = unlocked_session(client, make_video, clock)
    assert transcribe(client, first).status_code == 200
    r = transcribe(client, second)
    assert r.status_code == 429 and "tu límite" in r.json()["detail"]


def test_repetir_la_peticion_no_gasta_cupo(client, make_video, clock, monkeypatch):
    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", "1")
    sid = unlocked_session(client, make_video, clock)
    for _ in range(4):                                   # la misma sesión, varias veces
        assert transcribe(client, sid).status_code == 200


def test_un_error_de_configuracion_no_gasta_cupo(client, make_video, clock, monkeypatch):
    from app import main
    from app.transcription import TranscriptionConfigError, FakeTranscriber

    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", "1")
    sid = unlocked_session(client, make_video, clock)

    def not_configured():
        raise TranscriptionConfigError("Falta configurar GROQ_API_KEY en el servidor.")

    monkeypatch.setattr(main, "get_transcriber", not_configured)
    assert transcribe(client, sid).status_code == 503
    monkeypatch.setattr(main, "get_transcriber", lambda: FakeTranscriber())
    assert transcribe(client, sid).status_code == 200    # el intento fallido no contó


def test_cero_desactiva_los_limites(client, make_video, clock, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "0")
    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY", "0")
    monkeypatch.setenv("VIREVO_TRANSCRIPTIONS_PER_DAY_PER_IP", "0")
    for i in range(3):
        sid = unlocked_session(client, make_video, clock, name=f"v{i}.mp4")
        assert transcribe(client, sid).status_code == 200


def test_valor_invalido_usa_el_predeterminado(client, make_video, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "muchos")
    assert upload(client, make_video(7)).status_code == 200


# --- IP detrás de un proxy ---------------------------------------------------

def test_sin_proxy_una_ip_falsificada_no_evita_el_limite(client, make_video, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "1")
    video = make_video(7)
    with open(video, "rb") as f:
        data = f.read()

    def post(ip):
        return client.post("/videos/analizar", files={"file": ("a.mp4", data, "video/mp4")},
                           headers={"X-Forwarded-For": ip})

    assert post("1.1.1.1").status_code == 200
    assert post("2.2.2.2").status_code == 429            # el encabezado se ignora


def test_con_proxy_cada_ip_real_cuenta_por_separado(client, make_video, monkeypatch):
    monkeypatch.setenv("VIREVO_UPLOADS_PER_HOUR_PER_IP", "1")
    monkeypatch.setenv("VIREVO_TRUST_PROXY", "1")
    with open(make_video(7), "rb") as f:
        data = f.read()

    def post(ip):
        return client.post("/videos/analizar", files={"file": ("a.mp4", data, "video/mp4")},
                           headers={"X-Forwarded-For": ip})

    assert post("1.1.1.1, 10.0.0.1").status_code == 200  # se toma la primera de la lista
    assert post("2.2.2.2").status_code == 200
    assert post("1.1.1.1").status_code == 429
