FROM python:3.12-slim

# FFmpeg (el de Debian incluye libass para incrustar subtítulos) y fuentes: sin fuentes
# instaladas los subtítulos no se dibujan. Liberation Sans sustituye a Arial.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fontconfig fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

ENV VIREVO_DATA=/data
EXPOSE 8000

# Un solo proceso a propósito: las tareas en segundo plano y la recuperación al arrancar
# suponen un único servidor.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
