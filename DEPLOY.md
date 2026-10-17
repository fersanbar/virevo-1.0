# Publicar VIREVO

> Estos archivos de Docker no se probaron en el entorno donde se escribieron (no tenía Docker).
> Los tests del backend y la sintaxis del compose sí se verificaron, pero la primera vez que
> construyas las imágenes puede que haya que ajustar algo. Pega aquí cualquier error y se corrige.

## Estructura esperada

```
Virevo/
  docker-compose.yml
  backend/    (con Dockerfile, .env, app/, requirements.txt)
  frontend/   (con Dockerfile, Caddyfile, package.json, src/)
```

Si tus carpetas se llaman distinto, cambia `./backend` y `./frontend` en `docker-compose.yml`.

## 1. Probarlo primero en tu computadora

1. Instala Docker Desktop y ábrelo.
2. Crea `backend/.env` (copia `backend/.env.example`) con tu `GROQ_API_KEY`.
3. En la carpeta `Virevo`, en PowerShell:
   ```
   $env:VIREVO_DOMAIN="http://localhost"
   docker compose up --build
   ```
4. Abre http://localhost. Deben funcionar el video, los anuncios, los subtítulos y la descarga.

Para apagarlo: `Ctrl+C`, y `docker compose down` para quitar los contenedores.

## 2. Publicarlo en internet

1. **Servidor.** Un VPS Linux con Docker instalado. Recomendado: 2 CPU y 4 GB de RAM. Crear el video
   con subtítulos re-codifica el video y consume bastante CPU; con 1 GB se queda corto.
   Disco: 40 GB o más.
2. **Dominio.** Crea un registro DNS tipo A que apunte tu dominio (o subdominio) a la IP del servidor.
3. **Puertos.** Abre el 80 y el 443 en el firewall del servidor.
4. **Archivos.** Copia la carpeta `Virevo` al servidor y crea `backend/.env` con tus claves.
5. **Arrancar.** Dentro de la carpeta:
   ```
   VIREVO_DOMAIN=tudominio.com docker compose up -d --build
   ```
   Caddy consigue el certificado HTTPS por su cuenta (puede tardar un minuto).
6. Entra a https://tudominio.com y haz una prueba completa.

Comandos útiles: `docker compose logs -f` (ver qué pasa), `docker compose ps` (estado),
`docker compose down` (apagar), y para actualizar el código: `docker compose up -d --build`.

## 3. Antes de invitar a creadores

- **Tu gasto.** Los límites por defecto son 10 videos por hora por IP, 15 transcripciones por día por IP y 300
  transcripciones por día en total. Ajústalos en `backend/.env` (ver `.env.example`).
  Además fija un tope de gasto o saldo en tu cuenta de Groq.
- **Privacidad.** Los videos se guardan 2 horas en tu servidor y el audio se envía a Groq para transcribirlo.
  Avisa esto a los usuarios en un aviso de privacidad antes de recibir videos de terceros, y revisa los
  términos de privacidad del plan de Groq que uses. Esto no es asesoría legal.
- **Anuncios.** Siguen siendo simulados: todavía no generan ingresos. Con el sitio ya publicado puedes
  solicitar una red de anuncios real.
- **Un solo servidor.** El backend corre como un único proceso a propósito. No lo escales a varias copias
  sin antes cambiar la forma en que se guardan las tareas en segundo plano.
