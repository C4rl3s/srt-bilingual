# Backend — srt-bilingual

API FastAPI que inventaría la biblioteca de vídeo y subtítulos (también las pistas
de dentro de los vídeos, con ffmpeg) y genera los `.srt` bilingües, por traducción
(Azure Translator o DeepL, según su cupo libre) o por fusión con un coreano
existente. Gestionado con
[uv](https://docs.astral.sh/uv/); base de datos SQLite.

## Puesta en marcha

```powershell
uv sync                                          # instala dependencias en .venv
cp .env.example .env                             # claves de Azure y/o DeepL para traducir
uv run alembic upgrade head                      # crea/actualiza la base de datos
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 · OpenAPI: http://localhost:8000/docs
- Para los subtítulos incrustados en los vídeos hace falta **ffmpeg** (`ffprobe` y
  `ffmpeg`) en el `PATH`, o su ruta en `FFPROBE_PATH`/`FFMPEG_PATH`. En Windows:
  `winget install Gyan.FFmpeg`. Sin él, todo lo demás funciona y el progreso del
  sondeo (`GET /scan/sondeo`) dice que falta.

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
│                      translate, renombrado, videos
└── services/
    ├── scanner.py       recorre el disco y reconcilia la base de datos
    ├── obras.py         agrupa vídeos y subtítulos en obras; dónde va el bilingüe
    ├── library_tree.py  árbol de la biblioteca, derivado de las rutas
    ├── bilingual.py     compone y escribe el bilingüe (escritura atómica)
    ├── trabajos.py      crea y ejecuta los trabajos en segundo plano
    ├── mkv/
    │   ├── sondeo.py       pistas de subtítulo de cada vídeo (ffprobe, en segundo plano)
    │   └── extraccion.py   extrae las pistas de texto (ffmpeg, una pasada) a la caché
    ├── subtitles/
    │   ├── srt_parser.py   parseo, idioma por nombre y por contenido
    │   ├── ass_parser.py   parseo de ASS: solo el diálogo (sin carteles ni karaoke)
    │   ├── lectura.py      lee un subtítulo, sea .srt o pista extraída
    │   ├── lineas.py       líneas de un bloque: unidas al traducir, repartidas al volver
    │   ├── naming.py       convención de nombres
    │   ├── seleccion.py    elige el origen ES/EN y el coreano de cada obra
    │   ├── alineacion.py   alinea un coreano existente con el origen (fusión)
    │   └── renombrado.py   propone y aplica nombres al estilo de Plex
    └── translation/
        ├── base.py            Protocol Translator (+ ConCupo) y excepciones
        ├── deepl_provider.py  DeepL con el SDK oficial (informa de su cupo)
        ├── azure_provider.py  Azure Translator por REST con httpx (no informa)
        ├── registry.py        de un nombre a un proveedor; límites configurados
        ├── consumo.py         cupo de cada proveedor: API o registro del mes
        └── eleccion.py        elige proveedor según el cupo libre
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
- **Una pista incrustada es un subtítulo más**: una fila de `subtitle_file` con
  `video_id`, candidata de la obra de su vídeo junto a los `.srt` de al lado. Su
  `ruta` es `<vídeo>#<índice>`, que no es un fichero: se lee siempre con
  `subtitles/lectura.leer_bloques`, nunca por la ruta.
- **Un trabajo con pistas empieza extrayéndolas** (fase `EXTRAYENDO`: lee el vídeo
  entero, 1–1,5 min por episodio por la red) y revisa lo elegido con el texto de
  verdad: si la pista resulta ser un forzado u otro idioma, falla con el motivo; si
  el texto supera lo reservado y el proveedor ya no llega, falla antes de enviar
  nada. El bilingüe sale siempre como `.srt` junto al vídeo: el MKV no se toca.
- **Ningún fichero fuera de `services/translation/` conoce a un proveedor
  concreto**: añadir uno es un módulo nuevo y una entrada en `registry.py`.
- **El proveedor de cada traducción se elige por cupo**: el primero de
  `TRANSLATION_PROVIDERS` con cupo libre para toda la película (con un 5 % de
  margen). El cupo sale de la API del proveedor si la tiene (DeepL) o del
  **registro de la app** si no (Azure): la suma de `num_caracteres` de sus trabajos
  en el mes, que no ve lo gastado con esa clave fuera de la app. Lo que falta por
  enviar de los trabajos en cola queda reservado.

## Comandos

```powershell
uv run pytest                    # tests (ninguno llama a un proveedor real: ver conftest.py)
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
| `POST` | `/scan` | Escanea las carpetas marcadas (o las de `carpeta_ids`) y deja en segundo plano el sondeo de las pistas de los vídeos nuevos o cambiados |
| `GET` | `/scan/sondeo` | Progreso del sondeo de pistas: hechos, total y errores |
| `GET` | `/library/tree` | Árbol de la biblioteca hasta la obra, con estado, origen y coreano propuestos |
| `GET` | `/subtitles` | Lista los subtítulos. Filtros: `?estado=` y `?idioma=` |
| `GET` | `/subtitles/{id}` | Detalle de un subtítulo |
| `GET` | `/subtitles/{id}/candidatos` | Candidatos de su obra con motivo de descarte, calidad de la fusión y una muestra. `?origen_id=` para un origen elegido a mano |
| `POST` | `/translate` | Encola bilingües (`202`). Fusión si hay coreano; `forzar_traduccion` para traducir igualmente. Asigna el proveedor por cupo, o usa el de `proveedor` si se pide (con la misma comprobación de clave y cupo); si no cabe, la obra va a `rechazados` |
| `GET` | `/translate/jobs` | Trabajos (`?estado=`, `?activos=`) |
| `GET` | `/translate/jobs/{id}` | Estado y progreso de un trabajo |
| `GET` | `/translate/cupos` | Cupo de cada proveedor configurado, en orden de preferencia: usados, reservados, límite, libre y fuente de la cifra (API del proveedor o registro de la app) |
| `POST` | `/videos/{id}/extraer` | Extrae en segundo plano las pistas de texto del vídeo (`202`), para ver muestra y calidad de fusión antes de generar. Su estado sale en los candidatos |
| `GET` | `/renombrado/propuestas` | Renombrados propuestos a la nomenclatura de Plex |
| `POST` | `/renombrado` | Aplica los confirmados; nunca sobrescribe |

## Documentación

`docs/` en la raíz del repo: modelo de datos (`modelo-datos.md`), planes y
bitácoras de cada fase.
