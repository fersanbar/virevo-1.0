import httpx
import pytest

from app.audio import AudioExtractionError, extract_audio
from app.media import get_duration_seconds
from app.transcription import (
    FakeTranscriber,
    HttpWhisperTranscriber,
    TranscriptionConfigError,
    TranscriptionError,
    get_transcriber,
)


def make_transcriber(handler, model="whisper-large-v3-turbo"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpWhisperTranscriber("https://api.groq.com/openai/v1", "clave-123", model, client)


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"audio de mentira")
    return path


def ok_handler(captured=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["request"] = request
            captured["body"] = request.read()
        return httpx.Response(200, json={"segments": [
            {"start": 0.0, "end": 2.5, "text": " Hola a todos "},
            {"start": 2.5, "end": 4.0, "text": "   "},                 # vacío: se descarta
            {"start": 4.0, "end": 3.0, "text": "tiempos invertidos"},   # inválido: se descarta
            {"start": 4.0, "end": 6.1, "text": "bienvenidos al canal"},
        ]})
    return handler


def test_pide_segmentos_con_tiempos_y_parsea_la_respuesta(audio):
    captured = {}
    segments = make_transcriber(ok_handler(captured)).transcribe(audio, "es")

    request, body = captured["request"], captured["body"]
    assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer clave-123"
    for expected in (b"whisper-large-v3-turbo", b"verbose_json", b"timestamp_granularities[]",
                     b'name="language"', b"segment"):
        assert expected in body

    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.0, 2.5, "Hola a todos"),
        (4.0, 6.1, "bienvenidos al canal"),
    ]


def test_sin_idioma_no_manda_el_campo(audio):
    captured = {}
    make_transcriber(ok_handler(captured)).transcribe(audio, None)
    assert b'name="language"' not in captured["body"]


@pytest.mark.parametrize("status,fragment", [
    (401, "clave"), (403, "clave"), (413, "demasiado grande"),
    (429, "límite"), (500, "respondió con un error"),
])
def test_traduce_los_errores_del_proveedor(audio, status, fragment):
    transcriber = make_transcriber(lambda request: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(TranscriptionError) as exc:
        transcriber.transcribe(audio, "es")
    assert fragment in str(exc.value)


def test_error_de_red(audio):
    def handler(request):
        raise httpx.ConnectError("sin internet")

    with pytest.raises(TranscriptionError) as exc:
        make_transcriber(handler).transcribe(audio, "es")
    assert "conectar" in str(exc.value)


def test_respuesta_sin_voz(audio):
    transcriber = make_transcriber(lambda request: httpx.Response(200, json={"segments": []}))
    with pytest.raises(TranscriptionError) as exc:
        transcriber.transcribe(audio, "es")
    assert "No detectamos voz" in str(exc.value)


def test_respuesta_que_no_es_json(audio):
    transcriber = make_transcriber(lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(TranscriptionError):
        transcriber.transcribe(audio, "es")


def test_audio_demasiado_grande(audio, monkeypatch):
    monkeypatch.setattr("app.transcription.MAX_AUDIO_BYTES", 3)
    with pytest.raises(TranscriptionError):
        make_transcriber(ok_handler()).transcribe(audio, "es")


# --- Selección de proveedor --------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("VIREVO_FAKE_TRANSCRIBER", "VIREVO_STT_PROVIDER", "VIREVO_STT_MODEL",
                 "GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_por_defecto_usa_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-1")
    t = get_transcriber()
    assert t.base_url == "https://api.groq.com/openai/v1" and t.model == "whisper-large-v3-turbo"


def test_se_puede_cambiar_a_openai_y_de_modelo(monkeypatch):
    monkeypatch.setenv("VIREVO_STT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    monkeypatch.setenv("VIREVO_STT_MODEL", "otro-modelo")
    t = get_transcriber()
    assert t.base_url == "https://api.openai.com/v1" and t.model == "otro-modelo"


def test_sin_clave_explica_cual_falta():
    with pytest.raises(TranscriptionConfigError) as exc:
        get_transcriber()
    assert "GROQ_API_KEY" in str(exc.value)


def test_proveedor_desconocido(monkeypatch):
    monkeypatch.setenv("VIREVO_STT_PROVIDER", "inventado")
    with pytest.raises(TranscriptionConfigError):
        get_transcriber()


def test_modo_de_mentira(monkeypatch):
    monkeypatch.setenv("VIREVO_FAKE_TRANSCRIBER", "1")
    assert isinstance(get_transcriber(), FakeTranscriber)


# --- Audio -------------------------------------------------------------------

def test_extrae_audio_mono_y_ligero(make_video, tmp_path):
    out = tmp_path / "a.mp3"
    extract_audio(make_video(9), out)
    assert abs(get_duration_seconds(str(out)) - 9) < 1
    assert out.stat().st_size < 100_000


def test_video_sin_pista_de_audio(make_video, tmp_path):
    with pytest.raises(AudioExtractionError) as exc:
        extract_audio(make_video(5, audio=False), tmp_path / "a.mp3")
    assert "no tiene pista de audio" in str(exc.value)


def test_archivo_que_no_es_video(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"nada")
    with pytest.raises(AudioExtractionError):
        extract_audio(bad, tmp_path / "a.mp3")
