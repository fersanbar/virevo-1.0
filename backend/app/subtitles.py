"""Formatos de subtítulos: ASS (para incrustar en el video) y SRT (para descargar).

En el video incrustado cada subtítulo ocupa UNA sola línea: las frases largas se parten en
trozos que caben en el ancho del video y el tiempo de la frase se reparte entre ellos según
su largo. El archivo .srt conserva las frases completas (YouTube y otras plataformas ya
ajustan las líneas por su cuenta).

El tamaño de letra y los márgenes se calculan a partir de la resolución REAL del video,
así los subtítulos se ven igual de proporcionados en un video horizontal de 1080p que en
uno vertical de celular. Estas proporciones se repiten en la vista previa del editor
(SubtitleEditor.tsx) para que lo que ves se parezca a lo que descargas.
"""

import math

FONT_NAME = "Arial"
FONT_RATIO = 0.055            # letra = 5.5 % del lado corto del video
CHAR_WIDTH_RATIO = 0.6        # ancho promedio de una letra (en negrita) = 60 % de su tamaño; estimación prudente
OUTLINE_RATIO = 0.09          # contorno negro = 9 % del tamaño de letra
SIDE_MARGIN_RATIO = 0.06      # margen izquierdo y derecho
LANDSCAPE_BOTTOM_RATIO = 0.07
PORTRAIT_BOTTOM_RATIO = 0.22  # en vertical se deja libre la zona que tapa la interfaz de TikTok/Reels/Shorts


def _ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_text(text: str) -> str:
    # En ASS, { } abre códigos de formato y \ inicia comandos: se neutralizan para que
    # un subtítulo escrito por el usuario nunca pueda romper el archivo.
    text = text.replace("\\", "/").replace("{", "(").replace("}", ")")
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    return "\\N".join(lines)


def max_chars_per_line(width: float, height: float) -> int:
    """Cuántos caracteres caben en una línea. Depende solo de la proporción del video
    (no de su resolución), por eso la vista previa del editor da el mismo resultado."""
    usable = width * (1 - 2 * SIDE_MARGIN_RATIO)
    return max(8, math.floor(usable / (min(width, height) * FONT_RATIO * CHAR_WIDTH_RATIO) + 1e-6))


def split_text(text: str, max_chars: int) -> list[str]:
    """Parte el texto en trozos de una línea, cortando entre palabras y de forma pareja."""
    words = text.split()
    if not words:
        return []
    total = len(" ".join(words))
    parts = math.ceil(total / max_chars)
    if parts <= 1:
        return [" ".join(words)]
    target = total / parts
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current_len = len(" ".join(current))
        too_long = bool(current) and current_len + 1 + len(word) > max_chars
        balanced = bool(current) and current_len >= target and len(chunks) < parts - 1
        if too_long or balanced:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    chunks.append(" ".join(current))
    return chunks


def single_line_cues(segments: list[dict], max_chars: int) -> list[dict]:
    """Convierte frases en subtítulos de una línea, repartiendo el tiempo según el largo."""
    cues = []
    for seg in segments:
        chunks = split_text(seg["text"], max_chars)
        if not chunks:
            continue
        total = sum(len(c) for c in chunks)
        span = seg["end"] - seg["start"]
        done = 0
        for chunk in chunks:
            start = seg["start"] + span * done / total
            done += len(chunk)
            end = seg["start"] + span * done / total
            cues.append({"start": start, "end": end, "text": chunk})
    return cues


def build_ass(segments: list[dict], width: int, height: int) -> str:
    font = max(12, round(min(width, height) * FONT_RATIO))
    outline = max(1.5, round(font * OUTLINE_RATIO, 1))
    side = round(width * SIDE_MARGIN_RATIO)
    bottom_ratio = PORTRAIT_BOTTOM_RATIO if height > width else LANDSCAPE_BOTTOM_RATIO
    bottom = round(height * bottom_ratio)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{FONT_NAME},{font},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},0,2,{side},{side},{bottom},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in single_line_cues(segments, max_chars_per_line(width, height)):
        text = _ass_text(cue["text"])
        if text:
            lines.append(
                f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},Default,,0,0,0,,{text}"
            )
    return "\n".join(lines) + "\n"


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(segments: list[dict]) -> str:
    blocks = []
    for seg in segments:
        # Una línea vacía terminaría el bloque en SRT, así que se descartan.
        text = "\n".join(l.strip() for l in seg["text"].splitlines() if l.strip())
        if text:
            blocks.append(
                f"{len(blocks) + 1}\n{_srt_time(seg['start'])} --> {_srt_time(seg['end'])}\n{text}\n"
            )
    return "\n".join(blocks)
