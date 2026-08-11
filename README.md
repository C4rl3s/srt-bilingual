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
cp .env.example .env                      # opcional (idioma destino, clave de DeepL)
uv run alembic upgrade head               # crea la base de datos SQLite
uv run uvicorn app.main:app --reload --port 8000
```

Las carpetas a vigilar **se añaden desde la interfaz**, no por configuración.

- API: http://localhost:8000
- Health: http://localhost:8000/health
- Docs (OpenAPI): http://localhost:8000/docs

> **Escucha solo en local.** El endpoint `/fs/browse` lista directorios de la
> máquina para que el selector de carpetas funcione. Deja uvicorn en `127.0.0.1`
> (el valor por defecto); no lo expongas con `--host 0.0.0.0`.

Endpoints disponibles:

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/folders` | Carpetas vigiladas, con sus contadores y último escaneo |
| `POST` | `/folders` | Añade una carpeta. Rechaza duplicados y solapamientos |
| `PATCH` | `/folders/{id}` | Marca o desmarca la carpeta para el escaneo (`activa`) |
| `DELETE` | `/folders/{id}` | Deja de vigilarla y borra sus subtítulos (cascada) |
| `GET` | `/fs/roots` | Unidades disponibles, para el selector de carpetas |
| `GET` | `/fs/browse` | Subdirectorios de una ruta, para navegar el disco |
| `POST` | `/scan` | Escanea las carpetas marcadas (o las de `carpeta_ids`) |
| `GET` | `/library/tree` | Árbol de la biblioteca hasta la obra, con su estado |
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
- [x] **Fase 2** — Gestión de carpetas desde la interfaz (explorador, alta/baja,
  selección para escanear) y árbol de la biblioteca hasta el capítulo, mostrando
  qué tiene ya su versión dual y qué no.
- [ ] **Fase 3** — Traducción multi-proveedor (DeepL) y generación del `.srt` bilingüe.
- [ ] **Fase 4** — Tracking de cuotas por proveedor.
- [ ] **Fase 5** — Soporte MKV (extracción/inyección de subtítulos embebidos).
