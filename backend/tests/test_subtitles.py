import pytest

from app.subtitles import build_ass, build_srt, max_chars_per_line, single_line_cues, split_text

SEGS = [{"start": 0.0, "end": 2.5, "text": "Hola a todos"},
        {"start": 3661.256, "end": 3662.0, "text": "Segunda línea"}]


def style_line(ass: str) -> list[str]:
    return next(l for l in ass.splitlines() if l.startswith("Style:")).split(":", 1)[1].split(",")


def test_ass_usa_la_resolucion_real_del_video():
    ass = build_ass(SEGS, 1920, 1080)
    assert "PlayResX: 1920" in ass and "PlayResY: 1080" in ass


def test_la_letra_crece_con_la_resolucion():
    small = int(style_line(build_ass(SEGS, 640, 360))[2])
    big = int(style_line(build_ass(SEGS, 1920, 1080))[2])
    assert abs(big - small * 3) <= 2              # 3x la resolución, ~3x la letra (redondeo)


def test_vertical_sube_los_subtitulos_para_no_quedar_bajo_la_interfaz():
    landscape_margin = int(style_line(build_ass(SEGS, 1920, 1080))[-2]) / 1080
    portrait_margin = int(style_line(build_ass(SEGS, 1080, 1920))[-2]) / 1920
    assert portrait_margin > landscape_margin * 2


def test_tiempos_ass():
    ass = build_ass(SEGS, 640, 360)
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,Hola a todos" in ass
    assert "1:01:01.26,1:01:02.00" in ass


def test_el_texto_del_usuario_no_puede_romper_el_archivo():
    evil = [{"start": 0, "end": 1, "text": "{\\an8}hola\\Nmundo\n\n  segunda  "}]
    line = next(l for l in build_ass(evil, 640, 360).splitlines() if l.startswith("Dialogue"))
    text = line.split(",,", 1)[1]
    assert "{" not in text and "}" not in text and "\\n" not in text.replace("\\N", "")
    assert "/N" in text                      # el "\N" escrito por el usuario queda como texto inocuo
    assert "\\N" not in text.replace("/N", "")   # una sola línea: los saltos se vuelven espacios
    assert text.endswith("mundo segunda")


def test_srt_formato_y_numeracion():
    assert build_srt(SEGS) == (
        "1\n00:00:00,000 --> 00:00:02,500\nHola a todos\n\n"
        "2\n01:01:01,256 --> 01:01:02,000\nSegunda línea\n"
    )


def test_srt_descarta_lineas_vacias_dentro_de_un_subtitulo():
    srt = build_srt([{"start": 0, "end": 1, "text": "uno\n\n\ndos"}])
    assert "uno\ndos" in srt and "\n\n\n" not in srt


# --- Una sola línea a la vez ------------------------------------------------

LONG = "Hola a todos, bienvenidos a mi canal de videojuegos, hoy jugamos una partida increíble"

# Estos mismos casos se verificaron contra la versión de TypeScript (src/captions.ts):
# la vista previa del editor y el video final deben partir el texto igual.
SPLIT_CASES = [
    ("Hola a todos", 47, ["Hola a todos"]),
    (LONG, 47, ["Hola a todos, bienvenidos a mi canal de", "videojuegos, hoy jugamos una partida increíble"]),
    (LONG, 26, ["Hola a todos, bienvenidos", "a mi canal de videojuegos,", "hoy jugamos una partida", "increíble"]),
    ("uno dos tres cuatro cinco seis", 10, ["uno dos", "tres", "cuatro", "cinco seis"]),
    ("  espacios \n\n y   saltos  ", 12, ["espacios y", "saltos"]),
    ("supercalifragilisticoespialidoso corta", 10, ["supercalifragilisticoespialidoso", "corta"]),
    ("", 20, []),
]


@pytest.mark.parametrize("text,max_chars,expected", SPLIT_CASES)
def test_split_text(text, max_chars, expected):
    assert split_text(text, max_chars) == expected


def test_ningun_trozo_pasa_del_limite_salvo_palabras_gigantes():
    for chunk in split_text(LONG * 3, 30):
        assert len(chunk) <= 30


def test_el_tiempo_se_reparte_sin_huecos_ni_solapes():
    cues = single_line_cues([{"start": 10.0, "end": 16.0, "text": LONG}], 26)
    assert len(cues) == 4
    assert cues[0]["start"] == 10.0 and cues[-1]["end"] == pytest.approx(16.0)
    for a, b in zip(cues, cues[1:]):
        assert a["end"] == pytest.approx(b["start"])
    # un trozo más largo recibe más tiempo
    assert cues[0]["end"] - cues[0]["start"] > cues[3]["end"] - cues[3]["start"]


def test_caben_menos_letras_por_linea_en_vertical():
    assert max_chars_per_line(1280, 720) > max_chars_per_line(720, 1280)
    assert max_chars_per_line(1280, 720) == max_chars_per_line(640, 360)   # no depende de la resolución


def test_ass_genera_un_dialogo_por_trozo():
    ass = build_ass([{"start": 0, "end": 6, "text": LONG}], 720, 1280)
    assert ass.count("Dialogue:") == 4
    assert "\\N" not in ass


def test_el_srt_conserva_la_frase_completa():
    assert LONG in build_srt([{"start": 0, "end": 6, "text": LONG}])
