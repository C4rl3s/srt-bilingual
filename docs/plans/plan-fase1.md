# Retomar Fase 1 — cerrar el núcleo backend

## Context

Volvemos al proyecto tras ~1 mes de pausa. La **Fase 0** (esqueleto monorepo +
`/health` + front↔back) está terminada y commiteada. La **Fase 1** (núcleo
backend) tiene **todo el código escrito** pero nunca se llegó a ejecutar del todo:
lo bloqueaba **Smart App Control** de Windows (mataba el `python.exe` sin firmar de
uv). Ese bloqueo **ya está resuelto**: SAC = `0` y el sanity de imports pasa
(`from app.main import app` OK; tablas `library_folder`, `subtitle_file`).

Queda cerrar la Fase 1: **Alembic + tests + verificación e2e**. Nada de la Fase 1
está commiteado todavía (todo aparece como untracked/modified en `git status`).

## Estado verificado (2026-07-30)

- **SAC desactivado** (registro `VerifiedAndReputablePolicyState = 0`). Entorno OK.
- **Imports OK** vía `uv run` — el código de Fase 1 carga sin errores.
- **Código Fase 1 presente**: `config.py`, `db.py`, `models/` (enums + 2 tablas),
  `services/subtitles/` (modelo, naming, srt_parser), `services/scanner.py`,
  `schemas/` (scan, subtitle), `api/` (subtitles, scan), `main.py` con routers.
- **Falta por crear** (no existen aún):
  - `backend/alembic/` + `alembic.ini` — Alembic **no inicializado**.
  - Tests de Fase 1 — solo existe `tests/test_health.py` (de Fase 0).
  - `backend/.env` — solo hay `.env.example`.

## Plan para cerrar Fase 1

1. **Alembic (migraciones desde el día 1, sin `create_all`)**
   - `uv run alembic init alembic`
   - Editar `alembic/env.py`: `target_metadata = Base.metadata` (importar
     `app.models` para registrar las tablas) y tomar la URL de
     `app.config.settings` en vez de la de `alembic.ini`.
   - `uv run alembic revision --autogenerate -m "fase1: library_folder y subtitle_file"`
   - Revisar la migración generada y `uv run alembic upgrade head`.

2. **Tests (pytest, en `backend/tests/`)**
   - `conftest.py`: DB temporal + override de `get_db`.
   - `test_srt_parser.py`: parseo, `contar_caracteres` (sin índices ni tiempos),
     `contar_bloques`, `detectar_idioma_desde_nombre`.
   - `test_naming.py`: `derivar_nombre_bilingue`, `es_fichero_bilingue`.
   - `test_scanner.py`: reconciliación, cambios mtime+size, detección de traducido,
     huérfanos.
   - `test_subtitles_api.py`: `GET /subtitles` (filtros `?estado`/`?idioma`),
     `GET /subtitles/{id}`, `POST /scan`.
   - `uv run pytest` + `uv run ruff check .` en verde.

3. **Verificación e2e**
   - Crear `backend/.env` con `MEDIA_FOLDERS` apuntando a una carpeta de prueba con
     algún `.srt`.
   - `uv run uvicorn app.main:app --reload --port 8000`.
   - `POST /scan` → devuelve `ResumenEscaneo`; `GET /subtitles` → lista los ficheros
     detectados con su nº de caracteres y estado `PENDING`.

4. **(Opcional, tras revisión del usuario)** primer commit de Fase 1 — **solo si el
   usuario lo pide explícitamente**.

## Verificación

- `uv run pytest` verde y `uv run ruff check .` sin errores.
- Flujo e2e manual: `POST /scan` seguido de `GET /subtitles` sobre una carpeta real
  de prueba muestra los subtítulos con conteo correcto de caracteres.

## Notas

- Actualizar memoria `entorno-smart-app-control` (ya no está "pendiente reinicio":
  SAC = 0 confirmado) y `fase1-estado` al cerrar la fase. *(Fuera de plan mode.)*
- No commitear sin permiso explícito.
- Idioma de código/comentarios: español. ruff line-length 100, py314.
