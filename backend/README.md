# Backend — srt-bilingual

API FastAPI que inventaría la biblioteca de vídeo y subtítulos y genera los `.srt`
bilingües, por traducción o por fusión con un coreano existente. Gestionado con
[uv](https://docs.astral.sh/uv/); base de datos SQLite.

## Puesta en marcha

```powershell
uv sync                                          # instala dependencias en .venv
cp .env.example .env                             # rellena DEEPL_API_KEY para traducir
uv run alembic upgrade head                      # crea/actualiza la base de datos
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 · OpenAPI: http://localhost:8000/docs

Las carpetas a vigilar **no** se configuran aquí: se añaden desde la interfaz y
viven en la tabla `library_folder`. Las variables del `.env` están explicadas en
`.env.example` y en el README de la raíz.

> **Escucha solo en local.** `GET /fs/browse` lista directorios de la máquina para
> que el selector de carpetas funcione. Deja uvicorn en `127.0.0.1` (el valor por
> defecto); no lo expongas con `--host 0.0.0.0`.

## Estructura

```
app/
├── main.py            arranque, CORS, /health y alta de routers
├── config.py          Settings vía .env (pydantic-settings)
├── db.py              engine, SessionLocal, Base y la dependencia get_db
├── models/            library_folder, subtitle_file, media_file, translation_job
├── schemas/           DTOs Pydantic de entrada y salida
├── api/               folders, filesystem, scan, library, subtitles,
│                      translate, renombrado
└── services/
    ├── scanner.py       recorre el disco y reconcilia la base de datos
    ├── obras.py         agrupa vídeos y subtítulos en obras; dónde va el bilingüe
    ├── library_tree.py  árbol de la biblioteca, derivado de las rutas
    ├── bilingual.py     compone y escribe el bilingüe (escritura atómica)
    ├── trabajos.py      crea y ejecuta los trabajos en segundo plano
    ├── subtitles/
    │   ├── srt_parser.py   parseo, idioma por nombre y por contenido
    │   ├── naming.py       convención de nombres
    │   ├── seleccion.py    elige el origen ES/EN y el coreano de cada obra
    │   ├── alineacion.py   alinea un coreano existente con el origen (fusión)
    │   └── renombrado.py   propone y aplica nombres al estilo de Plex
    └── translation/
        ├── base.py            Protocol Translator (+ ConCupo) y excepciones
        ├── deepl_provider.py  DeepL con el SDK oficial
        └── registry.py        proveedor por TRANSLATION_PROVIDER
```

Ideas que explican el resto del diseño:

- **El disco es la fuente de verdad; la base de datos es un índice reconstruible.**
  Se puede borrar el `.db`, migrar de cero y reescanear sin perder nada. **Salvo
  `translation_job`**, que es historial de trabajos y de cupo consumido: sus claves
  a `subtitle_file` son `SET NULL` y guarda copia de sus rutas.
- **La obra no se almacena**: se deduce de las rutas (`services/obras.py`). La
  subcarpeta `Subs\` es transparente y, en una carpeta con un solo vídeo, todo es de
  ese vídeo.
- **Los tiempos del origen mandan**: el bilingüe conserva índice, inicio y fin de
  cada bloque del original. La traducción y la fusión producen lo mismo, un texto
  coreano por bloque, y `bilingual.py` no distingue de dónde viene.
- **Solo ES/EN → KO**. Sin origen en español o inglés, la obra no es elegible
  (`SIN_ORIGEN`).
- **Ningún fichero fuera de `services/translation/` conoce a DeepL**: cambiar de
  proveedor es añadir un módulo y una entrada en `registry.py`.

## Comandos

```powershell
uv run pytest                    # tests (ninguno llama a DeepL: usan TraductorFalso)
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
respecto a los modelos. Tras migrar, `uv run alembic check` lo comprueba.

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
| `GET` | `/library/tree` | Árbol de la biblioteca hasta la obra, con estado, origen y coreano propuestos |
| `GET` | `/subtitles` | Lista los subtítulos. Filtros: `?estado=` y `?idioma=` |
| `GET` | `/subtitles/{id}` | Detalle de un subtítulo |
| `GET` | `/subtitles/{id}/candidatos` | Candidatos de su obra con motivo de descarte, calidad de la fusión y una muestra. `?origen_id=` para un origen elegido a mano |
| `POST` | `/translate` | Encola bilingües (`202`). Fusión si hay coreano; `forzar_traduccion` para traducir igualmente |
| `GET` | `/translate/jobs` | Trabajos (`?estado=`, `?activos=`) |
| `GET` | `/translate/jobs/{id}` | Estado y progreso de un trabajo |
| `GET` | `/translate/cupos` | Cupo de cada proveedor configurado, en orden de preferencia: usados, reservados, límite, libre y fuente de la cifra (API del proveedor o registro de la app) |
| `GET` | `/renombrado/propuestas` | Renombrados propuestos a la nomenclatura de Plex |
| `POST` | `/renombrado` | Aplica los confirmados; nunca sobrescribe |

## Documentación

`docs/` en la raíz del repo: modelo de datos (`modelo-datos.md`), planes y
bitácoras de cada fase.
