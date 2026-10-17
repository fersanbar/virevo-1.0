import os
import subprocess
import tempfile

# Los tests NUNCA deben tocar tu carpeta data/ real: se apunta a una carpeta temporal
# antes de importar la app (que crea la base de datos al importarse).
os.environ["VIREVO_DATA"] = tempfile.mkdtemp(prefix="virevo-tests-")

import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import SessionStore
from app.transcription import FakeTranscriber


class FakeClock:
    """Reloj falso: permite 'esperar' 20 segundos en un test sin esperar de verdad."""

    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(main, "store", SessionStore(tmp_path / "test.db", clock=clock))
    monkeypatch.setattr(main, "UPLOADS_DIR", tmp_path / "uploads")
    # Por defecto los tests usan subtítulos de mentira: nunca llaman a un servicio real.
    monkeypatch.setattr(main, "get_transcriber", lambda: FakeTranscriber())
    return TestClient(main.app)


@pytest.fixture
def make_video(tmp_path):
    def _make(seconds, name="demo.mp4", audio=True):
        path = tmp_path / name
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s=64x64:r=1:d={seconds}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", str(seconds), "-shortest"]
        else:
            cmd += ["-an"]
        subprocess.run(cmd + [str(path)], capture_output=True, check=True)
        return path
    return _make
