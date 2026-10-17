import subprocess

import numpy as np
import pytest

from app.export import ExportError, burn_subtitles
from app.media import get_video_size

LONG = "Hola a todos, bienvenidos a mi canal de videojuegos, hoy jugamos una partida increible"


def black_video(path, w, h, seconds=3):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r=2:d={seconds}",
         "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", str(seconds), "-shortest", str(path)],
        capture_output=True, check=True,
    )
    return path


def frame_gray(video, t, w, h):
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(h, w)


def text_box(frame):
    ys, xs = np.nonzero(frame > 200)            # el texto es blanco sobre fondo negro
    assert len(ys) > 100, "no se ve ningún subtítulo en el video"
    return xs.min(), xs.max(), ys.min(), ys.max()


@pytest.mark.parametrize("w,h", [(640, 360), (360, 640), (1280, 720)])
def test_los_subtitulos_caben_y_se_adaptan_al_tamano(tmp_path, w, h):
    src = black_video(tmp_path / "in.mp4", w, h)
    out = tmp_path / "out.mp4"
    burn_subtitles(src, [{"start": 0, "end": 3, "text": LONG}], out)

    assert get_video_size(str(out)) == (w, h)
    font = min(w, h) * 0.055
    for t in (0.3, 1, 2, 2.5):                   # la frase se parte en trozos que se van sucediendo
        x0, x1, y0, y1 = text_box(frame_gray(out, t, w, h))
        assert x0 >= w * 0.04 and x1 <= w * 0.96, f"el texto se sale de los márgenes (t={t})"
        assert y0 > h * 0.5, "el texto debe quedar en la mitad de abajo"
        assert y1 < h * (0.82 if h > w else 0.96), "el texto no debe tapar el borde ni la zona de la interfaz"
        assert (y1 - y0) < font * 1.6, f"debe verse UNA sola línea, pero el texto mide {y1 - y0}px (t={t})"
    assert not (tmp_path / "in.ass").exists(), "el archivo temporal .ass debe borrarse"


def test_no_hay_subtitulo_fuera_de_su_tiempo(tmp_path):
    src = black_video(tmp_path / "in.mp4", 640, 360, seconds=4)
    out = tmp_path / "out.mp4"
    burn_subtitles(src, [{"start": 2, "end": 3, "text": "solo en el segundo 2"}], out)
    assert (frame_gray(out, 0.5, 640, 360) > 200).sum() == 0
    assert (frame_gray(out, 2.5, 640, 360) > 200).sum() > 100


def test_video_de_celular_con_rotacion_usa_el_tamano_que_se_ve(tmp_path):
    base = black_video(tmp_path / "base.mp4", 640, 360)
    rotated = tmp_path / "rot.mp4"
    subprocess.run(["ffmpeg", "-y", "-display_rotation", "90", "-i", str(base), "-c", "copy",
                    str(rotated)], capture_output=True, check=True)
    assert get_video_size(str(rotated)) == (360, 640)      # se ve vertical

    out = tmp_path / "out.mp4"
    burn_subtitles(rotated, [{"start": 0, "end": 3, "text": LONG}], out)
    assert get_video_size(str(out)) == (360, 640)
    for t in (0.3, 1, 2.5):
        x0, x1, y0, y1 = text_box(frame_gray(out, t, 360, 640))
        assert x0 >= 360 * 0.04 and x1 <= 360 * 0.96 and y1 < 640 * 0.82
        assert (y1 - y0) < 360 * 0.055 * 1.6


def test_conserva_el_audio(tmp_path):
    src = black_video(tmp_path / "in.mp4", 320, 180)
    out = tmp_path / "out.mp4"
    burn_subtitles(src, [{"start": 0, "end": 2, "text": "hola"}], out)
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert sorted(streams) == ["audio", "video"]


def test_archivo_que_no_es_video(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"nada")
    with pytest.raises(ExportError):
        burn_subtitles(bad, [{"start": 0, "end": 1, "text": "x"}], tmp_path / "o.mp4")
    assert not list(tmp_path.glob("*.part.mp4")) and not list(tmp_path.glob("*.ass"))
