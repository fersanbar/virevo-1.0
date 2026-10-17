import type { CSSProperties } from "react";
import type { Segment } from "./types";

// Estas reglas son una copia de backend/app/subtitles.py. La vista previa y el video final
// deben partir el texto igual; si cambias algo aquí, cámbialo también allá.
const FONT_RATIO = 0.055; // letra = 5.5 % del lado corto del video
const CHAR_WIDTH_RATIO = 0.6; // ancho promedio de una letra en negrita
const OUTLINE_RATIO = 0.09;
const SIDE_MARGIN_RATIO = 0.06;
const LANDSCAPE_BOTTOM_RATIO = 0.07;
const PORTRAIT_BOTTOM_RATIO = 0.22; // en vertical se deja libre la zona que tapa la interfaz de TikTok/Reels/Shorts

// Contamos caracteres reales (no unidades UTF-16) para dar el mismo resultado que Python con emojis.
const len = (text: string) => Array.from(text).length;

// Cuántos caracteres caben en una línea. Depende solo de la proporción del video.
export function maxCharsPerLine(width: number, height: number): number {
  const usable = width * (1 - 2 * SIDE_MARGIN_RATIO);
  return Math.max(8, Math.floor(usable / (Math.min(width, height) * FONT_RATIO * CHAR_WIDTH_RATIO) + 1e-6));
}

// Parte el texto en trozos de una línea, cortando entre palabras y de forma pareja.
export function splitText(text: string, maxChars: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  const total = len(words.join(" "));
  const parts = Math.ceil(total / maxChars);
  if (parts <= 1) return [words.join(" ")];
  const target = total / parts;
  const chunks: string[] = [];
  let current: string[] = [];
  for (const word of words) {
    const currentLen = len(current.join(" "));
    const tooLong = current.length > 0 && currentLen + 1 + len(word) > maxChars;
    const balanced = current.length > 0 && currentLen >= target && chunks.length < parts - 1;
    if (tooLong || balanced) {
      chunks.push(current.join(" "));
      current = [word];
    } else {
      current.push(word);
    }
  }
  chunks.push(current.join(" "));
  return chunks;
}

// Convierte frases en subtítulos de una línea, repartiendo el tiempo según el largo de cada trozo.
export function singleLineCues(segments: Segment[], maxChars: number): Segment[] {
  const cues: Segment[] = [];
  for (const seg of segments) {
    const chunks = splitText(seg.text, maxChars);
    if (chunks.length === 0) continue;
    const total = chunks.reduce((sum, c) => sum + len(c), 0);
    const span = seg.end - seg.start;
    let done = 0;
    for (const chunk of chunks) {
      const start = seg.start + (span * done) / total;
      done += len(chunk);
      const end = seg.start + (span * done) / total;
      cues.push({ start, end, text: chunk });
    }
  }
  return cues;
}

// Estilo del subtítulo según el tamaño con el que se ve el video en pantalla.
export function captionStyle(w: number, h: number): CSSProperties {
  const font = Math.max(10, Math.round(Math.min(w, h) * FONT_RATIO));
  const o = Math.max(1, Math.round(font * OUTLINE_RATIO));
  const side = Math.round(w * SIDE_MARGIN_RATIO);
  const bottom = Math.round(h * (h > w ? PORTRAIT_BOTTOM_RATIO : LANDSCAPE_BOTTOM_RATIO));
  const shadow = [
    [o, 0], [-o, 0], [0, o], [0, -o], [o, o], [-o, -o], [o, -o], [-o, o],
  ]
    .map(([x, y]) => `${x}px ${y}px 0 #000`)
    .join(", ");
  return { fontSize: font, left: side, right: side, bottom, textShadow: shadow };
}
