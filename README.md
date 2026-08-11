# srt-bilingual

Aplicación web para generar subtítulos **bilingües** (idioma original + traducción,
p. ej. coreano) a partir de ficheros `.srt`, pensada para usarse junto a una
biblioteca tipo Plex.

En lugar de fusionar dos `.srt` independientes (que casi nunca cuadran en tiempos),
parte del `.srt` original y traduce **bloque a bloque reutilizando las marcas de
tiempo originales**, evitando cualquier desalineación:

```
12
00:01:23,400 --> 00:01:25,900
Texto original en español
한국어 번역
```

## Stack

- **Backend:** Python + FastAPI, gestionado con [uv](https://docs.astral.sh/uv/). BD: SQLite.
- **Frontend:** React + TypeScript + Vite.
- **Traducción:** capa multi-proveedor (DeepL como primera implementación).

## Estructura

```
srt-bilingual/
├── backend/    # API FastAPI (uv)
└── frontend/   # SPA React + Vite
```

## Puesta en marcha (desarrollo)

### Backend

```bash
cd backend
uv sync                                   # instala dependencias en .venv
cp .env.example .env                      # y edita MEDIA_FOLDERS con tus carpetas
uv run alembic upgrade head               # crea la base de datos SQLite
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Health: http://localhost:8000/health
- Docs (OpenAPI): http://localhost:8000/docs

Endpoints disponibles:

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/scan` | Recorre las carpetas de `MEDIA_FOLDERS` e inventaría los `.srt` |
| `GET` | `/subtitles` | Lista los subtítulos. Filtros: `?estado=` y `?idioma=` |
| `GET` | `/subtitles/{id}` | Detalle de un subtítulo |

Tests:

```bash
cd backend
uv run pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

El frontend usa un proxy de Vite: las peticiones a `/api/*` se redirigen al backend
en el puerto 8000.

## Estado del proyecto

- [x] **Fase 0** — Esqueleto del proyecto y conexión front↔back (`/health`).
- [x] **Fase 1** — Modelos SQLite, scanner de carpetas, parser SRT y conteo de caracteres.
- [ ] **Fase 2** — Listado en React de subtítulos traducidos/pendientes.
- [ ] **Fase 3** — Traducción multi-proveedor (DeepL) y generación del `.srt` bilingüe.
- [ ] **Fase 4** — Tracking de cuotas por proveedor.
- [ ] **Fase 5** — Soporte MKV (extracción/inyección de subtítulos embebidos).
