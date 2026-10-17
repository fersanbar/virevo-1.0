# VIREVO backend

FastAPI + SQLite. Necesita Python 3.10+ y FFmpeg instalado.

**FFmpeg debe ser la versión completa** (con soporte de subtítulos, libass), porque con ella se
incrustan los subtítulos en el video. En Windows: `winget install Gyan.FFmpeg` (versión completa).
Para comprobarlo: `ffmpeg -filters` debe listar `ass` y `subtitles`. Si no, la app avisa con un
mensaje claro al crear el video.

## Correrlo

```
cd virevo-backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

## Configuración (archivo .env)

Copia `.env.example` como `.env` (misma carpeta) y llena tus claves. El `.env` nunca se sube
a un repositorio (ya está en `.gitignore`). Reinicia el servidor después de cambiarlo.

| Variable | Para qué sirve |
|---|---|
| `GROQ_API_KEY` | Clave de Groq (proveedor de transcripción por defecto) |
| `VIREVO_STT_PROVIDER` | `groq` (por defecto) u `openai` |
| `OPENAI_API_KEY` | Solo si usas `openai` |
| `VIREVO_STT_MODEL` | Opcional: cambiar el modelo del proveedor |
| `VIREVO_AD_SECONDS` | Opcional: acortar los anuncios mientras pruebas (ej. 3) |
| `VIREVO_FAKE_TRANSCRIBER` | `1` = subtítulos de mentira, sin gastar nada |

### Conseguir la clave de Groq

1. Crea una cuenta en https://console.groq.com
2. Entra a **API Keys** y crea una clave (empieza con `gsk_`).
3. Pégala en `.env`: `GROQ_API_KEY=gsk_...`

### Probar el proveedor sin abrir la app

```
python -m app.probar ruta/a/tu/video.mp4 es
```
Imprime los subtítulos con su hora. Si esto funciona, la app también.

## Por qué Groq y no OpenAI

OpenAI retira `whisper-1` el 26-feb-2027, y su reemplazo (`gpt-transcribe`) no devuelve marcas de
tiempo. Groq ofrece Whisper con el mismo formato de API (compatible con OpenAI), con tiempos por
segmento y un precio por hora de audio mucho menor. Cambiar de proveedor es cambiar `.env`.
Antes de usar la app con clientes reales, revisa los términos de privacidad del plan que uses.

## Datos

Los videos y la base de datos se guardan en `data/` (se crea sola). Para empezar de cero,
apaga el servidor y borra esa carpeta. Las sesiones y sus videos se limpian a las 2 horas.

## Tests

```
python -m pytest
```
Los tests usan una carpeta temporal y subtítulos simulados: no tocan tu `data/` ni llaman a ningún servicio.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| POST | /videos/analizar | Recibe el video, mide su duración, crea la sesión y devuelve el plan de anuncios |
| GET | /sesiones/{id} | Estado de la sesión |
| POST | /sesiones/{id}/anuncios/iniciar | El servidor anota la hora de inicio del anuncio |
| POST | /sesiones/{id}/anuncios/completar | Cuenta el anuncio solo si pasó el tiempo completo |
| POST | /sesiones/{id}/transcribir | Genera los subtítulos (403 sin anuncios; no cobra dos veces) |
| GET | /sesiones/{id}/subtitulos | Estado de la transcripción y los subtítulos |
| PUT | /sesiones/{id}/subtitulos | Guarda los subtítulos editados (invalida el video exportado antes) |
| POST | /sesiones/{id}/exportar | Crea el video con los subtítulos incrustados (en segundo plano) |
| GET | /sesiones/{id}/exportacion | Estado de la exportación |
| GET | /sesiones/{id}/descargar/video | Descarga el video con subtítulos |
| GET | /sesiones/{id}/descargar/srt | Descarga el archivo .srt |

## Cómo se ven los subtítulos incrustados

Cada subtítulo ocupa **una sola línea**: las frases largas se parten en trozos que caben en el ancho
del video, y el tiempo de la frase se reparte entre ellos según su largo. El archivo `.srt` conserva
las frases completas. Cuánto cabe en una línea depende de `FONT_RATIO` y `CHAR_WIDTH_RATIO` en
`app/subtitles.py` (y de su copia en `frontend/src/captions.ts`): si quieres letra más chica o
más grande, cambia `FONT_RATIO` en los dos archivos.

El tamaño de letra y los márgenes se calculan con la resolución real del video (y su rotación, en
videos de celular), así que se ven proporcionados en horizontal y en vertical. En vertical se suben
para no quedar bajo la interfaz de TikTok, Reels y Shorts. Las proporciones están en
`app/subtitles.py`; si las cambias, cámbialas también en `SubtitleEditor.tsx` para que la vista
previa siga pareciéndose al resultado.
