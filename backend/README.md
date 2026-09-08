# Backend — srt-bilingual

API FastAPI que inventaría la biblioteca de vídeo y subtítulos y, más adelante,
generará los `.srt` bilingües. Gestionado con [uv](https://docs.astral.sh/uv/);
base de datos SQLite.

## Puesta en marcha

```powershell
uv sync                                          # instala dependencias en .venv
cp .env.example .env                             # opcional (idioma destino, DeepL)
uv run alembic upgrade head                      # crea/actualiza la base de datos
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 · OpenAPI: http://localhost:8000/docs

Las carpetas a vigilar **no** se configuran aquí: se añaden desde la interfaz y
viven en la tabla `library_folder`.

> **Escucha solo en local.** `GET /fs/browse` lista directorios de la máquina para
> que el selector de carpetas funcione. Deja uvicorn en `127.0.0.1` (el valor por
> defecto); no lo expongas con `--host 0.0.0.0`.

## Estructura

```
app/
├── main.py            arranque, CORS, /health y alta de routers
├── config.py          Settings vía .env (pydantic-settings)
├── db.py              engine, SessionLocal, Base y la dependencia get_db
├── models/            tablas ORM: library_folder, subtitle_file, media_file
├── schemas/           DTOs Pydantic de entrada y salida
├── api/               routers: folders, filesystem, scan, library, subtitles
└── services/
    ├── scanner.py       recorre el disco y reconcilia la base de datos
    ├── library_tree.py  árbol de la biblioteca, derivado de las rutas
    └── subtitles/       Bloque, parser SRT y convención de nombres
```

Dos ideas que explican el resto del diseño:

- **El disco es la fuente de verdad; la base de datos es un índice reconstruible.**
  Se puede borrar el `.db`, migrar de cero y reescanear sin perder nada.
- **El árbol de la biblioteca no se almacena**: se deriva de las rutas de
  `media_file` y `subtitle_file` en cada consulta.

## Comandos

```powershell
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format .             # formateo
uv add <paquete>                 # dependencia de runtime
uv add --dev <paquete>           # dependencia de desarrollo
```

### Migraciones (tras tocar un modelo de `app/models/`)

```powershell
uv run alembic revision --autogenerate -m "descripcion"   # generar
uv run alembic upgrade head                               # aplicar
uv run alembic current                                    # revisión aplicada
uv run alembic downgrade -1                               # deshacer la última
```

**Revisa siempre lo que genera `--autogenerate`**: no adivina renombrados, y una
columna `NOT NULL` sobre una tabla con filas necesita `server_default` o la
migración falla. `alembic/env.py` toma la URL de `app.config.settings`, no de
`alembic.ini`.

Los tests crean el esquema con `Base.metadata.create_all()` en vez de con Alembic,
así que **no detectan por sí solos** que una migración se haya quedado desfasada
respecto a los modelos.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/health` | Comprobación de salud |
| `GET` | `/folders` | Carpetas vigiladas, con contadores y último escaneo |
| `POST` | `/folders` | Añade una carpeta. Rechaza duplicados y solapamientos |
| `PATCH` | `/folders/{id}` | Marca o desmarca la carpeta para el escaneo |
| `DELETE` | `/folders/{id}` | Deja de vigilarla y borra lo suyo (cascada) |
| `GET` | `/fs/roots` | Unidades disponibles, para el selector |
| `GET` | `/fs/browse` | Subdirectorios de una ruta |
| `POST` | `/scan` | Escanea las carpetas marcadas (o las de `carpeta_ids`) |
| `GET` | `/library/tree` | Árbol de la biblioteca hasta la obra, con su estado |
| `GET` | `/subtitles` | Lista los subtítulos. Filtros: `?estado=` y `?idioma=` |
| `GET` | `/subtitles/{id}` | Detalle de un subtítulo |

## Documentación

`docs/` en la raíz del repo: modelo de datos, planes y bitácoras de cada fase.
