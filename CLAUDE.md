# CLAUDE.md — srt-bilingual

Guía de contexto para Claude Code. Léela al empezar cualquier sesión en este repo.

## Qué es y por qué existe

App web personal (uso doméstico, un solo usuario) para generar subtítulos
**bilingües** a partir de ficheros `.srt`, pensada para usarse junto a una
biblioteca **Plex**. Caso de uso real: ver películas/series con doble subtítulo
(p. ej. español/inglés + **coreano**), algo que ni las plataformas ni Plex
permiten de forma nativa.

**Idea central (resuelve el problema de alineación temporal):** en vez de fusionar
dos `.srt` independientes —que casi nunca cuadran en tiempos— se parte del `.srt`
original y se traduce **bloque a bloque reutilizando las marcas de tiempo
originales**. El resultado por bloque:

```
12
00:01:23,400 --> 00:01:25,900
Texto original en español
한국어 번역
```

## Stack

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | **Python + FastAPI** | Gestionado con **uv** (no pip/venv manual). Python **3.14**. |
| Base de datos | **SQLite** | Un solo usuario, sin servidor; fichero local. |
| Frontend | **React + TypeScript + Vite** | El usuario aprende React aquí; mantener el código claro y didáctico. |
| Traducción | Capa **multi-proveedor** | DeepL como primera implementación (SDK oficial). |
| MKV (futuro) | ffmpeg / pymkv2 | Extracción e inyección de subtítulos embebidos. |

Decisiones tomadas (no re-litigar sin motivo):
- Python+FastAPI sobre Java/Spring: ecosistema de subtítulos/MKV superior, más
  ligero para uso doméstico, y el usuario quiere aprender Python.
- SQLite sobre MySQL: un solo usuario, cero mantenimiento.
- Traducción con abstracción multi-proveedor desde el día 1 (el upgrade de contar
  caracteres por API y elegir proveedor al vuelo encaja sin reescribir).

## Arquitectura (monorepo dividido)

```
srt-bilingual/
├── CLAUDE.md          # este fichero
├── README.md          # docs de usuario / puesta en marcha
├── .gitignore
├── backend/           # API FastAPI (uv) — Python 3.14
│   ├── app/
│   │   ├── main.py            # arranque FastAPI + CORS + /health
│   │   ├── config.py          # (Fase 1) settings vía .env (pydantic-settings)
│   │   ├── db.py              # (Fase 1) engine + sesión SQLAlchemy
│   │   ├── models/            # (Fase 1) tablas ORM
│   │   ├── schemas/           # (Fase 1) Pydantic (DTOs request/response)
│   │   ├── api/               # (Fase 1+) routers: subtitles, scan, translate, usage
│   │   └── services/
│   │       ├── scanner.py     # (Fase 1) escaneo de carpetas
│   │       ├── srt_parser.py  # (Fase 1) parseo + conteo de caracteres
│   │       ├── bilingual.py   # (Fase 3) genera el .srt bilingüe
│   │       └── translation/
│   │           ├── base.py    # (Fase 3) interfaz Translator (protocol)
│   │           ├── deepl_provider.py
│   │           └── registry.py # (Fase 3+) selección de proveedor / quotas
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml         # deps + config de pytest y ruff
└── frontend/          # SPA React + Vite
    ├── src/App.tsx
    └── vite.config.ts         # proxy /api -> http://localhost:8000
```

> Nota: las carpetas marcadas `(Fase N)` aún no existen; se crean al llegar a esa
> fase. No las crees vacías por adelantado.

## Modelo de datos previsto (Fase 1)

- `library_folder` — carpetas a vigilar (las mismas compartidas en Plex).
- `subtitle_file` — ruta, idioma origen, nº caracteres (sin marcas de tiempo),
  nº líneas, estado (`PENDING`/`TRANSLATED`/`ERROR`), ruta del bilingüe generado,
  idioma destino, proveedor usado, `mtime`/hash (para no reescanear lo no cambiado),
  timestamps.
- `provider_usage` — proveedor, `año-mes`, caracteres consumidos, cuota mensual
  (sostiene los upgrades de tracking de cuotas).

## Convenciones

**General**
- Idioma del código y comentarios: **español** (nombres de dominio, docstrings,
  mensajes). Mantener la densidad de comentarios del código circundante.
- Estados/enums en mayúsculas: `PENDING`, `TRANSLATED`, `ERROR`.

**Backend (Python)**
- `snake_case` para funciones/variables/módulos; `PascalCase` para clases.
- Módulos y carpetas en `snake_case` y singular cuando es un servicio
  (`scanner.py`), plural para colecciones de tipos (`models/`, `schemas/`).
- Linter/formatter: **ruff** (`line-length = 100`, `target-version = py314`).
- Tests con **pytest** en `backend/tests/`, fichero `test_*.py`. `pythonpath = ["."]`
  ya configurado, así que los imports son `from app.main import app`.
- Type hints siempre que aporten claridad.

**Frontend (React/TS)**
- Componentes en `PascalCase`; hooks `useX`; ficheros de componente `PascalCase.tsx`.
- Las llamadas al backend van **siempre a `/api/...`** (el proxy de Vite reescribe
  `/api` → backend en `:8000`, quitando el prefijo). No hardcodear `localhost:8000`.

**Git**
- Rama principal: `main`. Commits estilo convencional (`feat:`, `chore:`, `fix:`…).
- No commitear sin que el usuario lo pida.

## Comandos habituales

```powershell
# Backend
cd backend
uv sync                                          # instalar deps
uv run uvicorn app.main:app --reload --port 8000 # API en :8000  (/docs para OpenAPI)
uv run pytest                                    # tests
uv run ruff check .                              # lint
uv add <paquete>                                 # añadir dependencia de runtime
uv add --dev <paquete>                           # añadir dependencia de desarrollo

# Frontend
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check (tsc) + build de producción
```

## Entorno (importante)

- **SO:** Windows 11, shell **PowerShell** (la herramienta Bash POSIX no está
  disponible en este entorno).
- `uv` y `Node` se instalaron con **winget** (`astral-sh.uv`, `OpenJS.NodeJS.LTS`).
  Si una sesión no los encuentra en el PATH, recargar con:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`
- Versiones de referencia: uv 0.11.x, Node 24.x, Python 3.14.6, git 2.54.

## Estado del plan

Plan de desarrollo aprobado en 6 fases. Detalle de la Fase 0 en
`C:\Users\Beicon\.claude\plans\spicy-purring-dragon.md`.

- [x] **Fase 0 — Esqueleto + conexión front↔back.** Estructura del monorepo,
  backend con `/health` + CORS + test, frontend Vite consumiendo `/api/health`
  vía proxy. Verificado end-to-end. *(Repo iniciado; pendiente primer commit salvo
  que ya se haya hecho.)*
- [ ] **Fase 1 — Núcleo backend.** Config (.env), modelos SQLite, scanner de
  carpetas, parser SRT + conteo de caracteres (limpiando índices y marcas de
  tiempo), detección de estado. Endpoints: `GET /subtitles`, `POST /scan`,
  `GET /subtitles/{id}`.
- [ ] **Fase 2 — Frontend de consulta.** Listado usable (traducidos vs.
  pendientes) con nº de caracteres, filtros/búsqueda y botón de "escanear".
- [ ] **Fase 3 — Traducción + generación bilingüe.** Interfaz `Translator` +
  DeepL (batch), servicio `bilingual.py` reutilizando tiempos, selección de
  uno/varios subtítulos, registro de caracteres por trabajo. Traducción async vía
  `BackgroundTasks` de FastAPI (sin Celery).
- [ ] **Fase 4 — Optimización de cuotas.** Tabla de uso por proveedor/mes, panel
  en el front, selección de proveedor según cuota libre restante.
- [ ] **Fase 5 — Soporte MKV.** Extracción de subtítulos embebidos (ffmpeg/pymkv2)
  e inyección del track bilingüe.

## Notas / deuda técnica

- uv eligió **Python 3.14**. Si alguna librería futura (p. ej. MKV) no tuviera
  wheel para 3.14, fijar 3.12 con `uv python pin 3.12`.
- Warning de deprecación de `TestClient`/httpx (sugiere `httpx2`). Inofensivo;
  abordar cuando moleste.
- Idioma destino por defecto coreano (`KO`), pero hacerlo **configurable** por si
  se quiere otro par de idiomas.
