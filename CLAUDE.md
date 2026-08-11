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
│   │   ├── main.py            # arranque FastAPI + CORS + /health + routers
│   │   ├── config.py          # settings vía .env (pydantic-settings)
│   │   ├── db.py              # engine + sesión SQLAlchemy + get_db
│   │   ├── models/            # tablas ORM: enums, library_folder, subtitle_file
│   │   ├── schemas/           # Pydantic (DTOs request/response): scan, subtitle
│   │   ├── api/               # routers: subtitles, scan (+ translate/usage en Fase 3-4)
│   │   └── services/
│   │       ├── scanner.py     # escaneo y reconciliación disco ↔ BD
│   │       ├── subtitles/     # modelo (Bloque), naming, srt_parser
│   │       ├── bilingual.py   # (Fase 3) genera el .srt bilingüe
│   │       └── translation/
│   │           ├── base.py    # (Fase 3) interfaz Translator (protocol)
│   │           ├── deepl_provider.py
│   │           └── registry.py # (Fase 3+) selección de proveedor / quotas
│   ├── alembic/               # migraciones (env.py toma la URL de settings)
│   ├── alembic.ini
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml         # deps + config de pytest y ruff
└── frontend/          # SPA React + Vite
    ├── src/App.tsx
    └── vite.config.ts         # proxy /api -> http://localhost:8000
```

> Nota: las carpetas marcadas `(Fase N)` aún no existen; se crean al llegar a esa
> fase. No las crees vacías por adelantado.

## Modelo de datos

Esquema detallado (tablas, columnas, índices y diagrama): **`docs/modelo-datos.md`**
(fuente de verdad) y su versión visual autocontenida `docs/modelo-datos.html`.
Resumen:

- `library_folder` — carpetas a vigilar (las mismas compartidas en Plex). *(Fase 1)*
- `subtitle_file` — ruta, idioma origen, nº caracteres (sin marcas de tiempo),
  nº bloques, estado (`PENDING`/`TRANSLATED`/`ERROR`), ruta del bilingüe generado,
  idioma destino, proveedor usado, `mtime`+tamaño (para no reparsear lo no cambiado),
  timestamps. *(Fase 1)*
- `provider_usage` — proveedor, `año-mes`, caracteres consumidos, cuota mensual
  (sostiene el tracking de cuotas). *(pendiente, Fase 4)*

**Principio rector:** el sistema de ficheros es la fuente de verdad; la base de datos
es un índice reconstruible. Un escaneo siempre puede rehacerse desde cero.

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
uv run alembic upgrade head                      # aplicar migraciones (crea/actualiza la BD)
uv run uvicorn app.main:app --reload --port 8000 # API en :8000  (/docs para OpenAPI)
uv run pytest                                    # tests
uv run ruff check .                              # lint
uv run ruff format .                             # formateo
uv add <paquete>                                 # añadir dependencia de runtime
uv add --dev <paquete>                           # añadir dependencia de desarrollo

# Migraciones (tras tocar un modelo de app/models/)
uv run alembic revision --autogenerate -m "descripcion"  # generar; REVISAR siempre lo generado
uv run alembic upgrade head                              # aplicar
uv run alembic current                                   # revisión aplicada
uv run alembic downgrade -1                              # deshacer la última

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

## Aprendizaje (cierre de cada fase)

Este proyecto es también el vehículo con el que el usuario aprende Python y React.
Al **terminar cada fase** (código escrito, ejecutado y verificado) hay un repaso
docente con comandos globales propios:

| Comando | Cuándo | Qué hace |
|---|---|---|
| `/teachpy` | Fases con backend (1, 3, 4, 5) | Recorre **todo** el Python escrito en la fase y lo explica a nivel de lenguaje |
| `/teachreact` | Fases con frontend (2, 4) | Ídem con el código React/TS |

Definidos en `C:\Users\Beicon\.claude\commands\teachpy.md` y `teachreact.md`.

Cómo se comportan (importante, para no desvirtuarlos):

- **Por defecto son solo explicación**: índice de ficheros, recorrido de arriba
  abajo citando `fichero:línea`, centrado en lo **idiomático del lenguaje** y en el
  **por qué** de cada decisión. Nada de conceptos universales de programación —el
  usuario ya es desarrollador backend.
- **No proponen ejercicios ni examinan de entrada.** Ese es un modo aparte que
  activa el usuario ("ponme ejercicios", "examíname").
- En modo ejercicios se pregunta **siempre** antes: ¿practicar sobre el código real
  del proyecto (solo cambios que le convengan al proyecto) o con ejercicios
  originales aparte, fuera del código de producción? El proyecto tiene un propósito
  y no se deforma para practicar.
- En modo docente **no se modifica código** salvo petición explícita.

Al cerrar una fase, ofrecer el repaso; no darlo por hecho ni lanzarlo sin pedirlo.

## Estado del plan

Plan de desarrollo aprobado en 6 fases.

- [x] **Fase 0 — Esqueleto + conexión front↔back.** Estructura del monorepo,
  backend con `/health` + CORS + test, frontend Vite consumiendo `/api/health`
  vía proxy. Verificado end-to-end. Commit `225ff60`.
- [x] **Fase 1 — Núcleo backend.** Config (.env), modelos SQLite + Alembic, scanner
  de carpetas, parser SRT + conteo de caracteres (limpiando índices y marcas de
  tiempo), detección de estado. Endpoints: `GET /subtitles`, `POST /scan`,
  `GET /subtitles/{id}`. 48 tests en verde y verificación e2e hecha
  (2026-07-30). Bitácora: `docs/bitacora-fase1.md`. *(Sin commitear aún.)*
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
- [ ] **Al terminar — web de documentación.** Una sola web con secciones que
  reutilice todo lo escrito por el camino (bitácoras, decisiones, fases, modelo de
  datos). Esta sí va **en local y publicada en remoto**.

**Documentación:** vive en `docs/`, dentro del repo, y se versiona en el mismo
commit que el código que describe. Los HTML, autocontenidos (sin CDN) para abrirlos
con doble clic; los diagramas, Mermaid en markdown. Nada se publica fuera de la
máquina sin pedírselo antes al usuario.

## Notas / deuda técnica

- uv eligió **Python 3.14**. Si alguna librería futura (p. ej. MKV) no tuviera
  wheel para 3.14, fijar 3.12 con `uv python pin 3.12`.
- Warning de deprecación de `TestClient`/httpx (sugiere `httpx2`). Inofensivo;
  abordar cuando moleste.
- Idioma destino por defecto coreano (`KO`), configurable con `DEFAULT_TARGET_LANG`.
- Los tests crean el esquema con `Base.metadata.create_all()`, no con Alembic (más
  rápido). No detectan por sí solos que una migración se haya quedado desfasada
  respecto a los modelos; tras tocar un modelo, generar la migración y revisarla.
- `alembic.ini` conserva la línea `sqlalchemy.url` de la plantilla, pero es inerte:
  `alembic/env.py` la sobrescribe con `settings.database_url`.
- `backend/README.md` está vacío y `frontend/README.md` es la plantilla de Vite.
- Assets sobrantes de la plantilla en `frontend/` (`hero.png`, `react.svg`,
  `vite.svg`, `public/icons.svg`): no los referencia nadie.
