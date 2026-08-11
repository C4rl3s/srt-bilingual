# Bitácora — Fase 1 (Núcleo backend)

Registro de plan ↔ implementación de la Fase 1.

## Estado: **COMPLETADA** (2026-07-30)

Código escrito, ejecutado y verificado. **48 tests en verde**, `ruff check` y
`ruff format` limpios, y flujo end-to-end comprobado contra el servidor real.
Pendiente únicamente el commit (a decisión del usuario).

## Decisiones de diseño (tomadas con el usuario)

- **Principio rector:** el sistema de ficheros es la fuente de verdad; la DB es un
  índice reconstruible. El bilingüe vive en disco y es autoidentificable.
- Parser SRT con la librería **`srt`**; representación interna normalizada `Bloque`
  para no acoplar el dominio a la librería (costura multi-formato).
- Idioma origen **por sufijo del nombre** (acepta `es`/`spa`/`spanish`), enum
  canónico `Idioma` alineado con DeepL; flags `forced`/`sdh`/`cc`/`hi` se ignoran.
- **Alembic** desde el día 1 (no `create_all` en runtime).
- Escaneo **síncrono** (`POST /scan` devuelve un `ResumenEscaneo`).
- Ciclo de vida de carpetas: **hard-delete + re-escaneo** (no soft-disable). Quitar
  una carpeta de `.env` borra sus filas (cascada); lo traducido se redescubre.
- Convención de salida bilingüe (estructural): `<base>.<ORIGEN>-<DESTINO>.bilingue.srt`.
- `FormatoSubtitulo` enum (solo SRT) + columna `formato`, preparado para VTT/ASS.

## Implementado (ficheros)

Dependencias añadidas (uv): `sqlalchemy`, `pydantic-settings`, `alembic`, `srt`.

**Aplicación**

- `app/config.py` — `Settings` (pydantic-settings), propiedad `carpetas`.
- `app/db.py` — engine sync, `SessionLocal`, `Base`, `get_db`, listener
  `PRAGMA foreign_keys=ON`.
- `app/models/enums.py` — `EstadoSubtitulo`, `FormatoSubtitulo`, `Idioma`,
  `SUFIJOS_IDIOMA`, `TOKENS_FLAG`.
- `app/models/library_folder.py` — `CarpetaBiblioteca` (cascade a subtítulos).
- `app/models/subtitle_file.py` — `ArchivoSubtitulo` (FK ondelete CASCADE).
- `app/models/__init__.py` — reexporta modelos (para Alembic autogenerate).
- `app/services/subtitles/modelo.py` — dataclass `Bloque`.
- `app/services/subtitles/naming.py` — `derivar_nombre_bilingue`, `es_fichero_bilingue`.
- `app/services/subtitles/srt_parser.py` — `parsear`, `contar_caracteres`,
  `contar_bloques`, `detectar_idioma_desde_nombre`.
- `app/services/scanner.py` — `escanear(db)` (reconciliación, cambios mtime+size,
  detección de traducido, huérfanos).
- `app/schemas/scan.py` — `ResumenEscaneo`; `app/schemas/subtitle.py` — `SubtituloOut`.
- `app/api/subtitles.py` — `GET /subtitles` (filtros `?estado`/`?idioma`),
  `GET /subtitles/{id}`; `app/api/scan.py` — `POST /scan`.
- `app/main.py` — incluye los routers (sin prefijo `/api`).

**Migraciones**

- `alembic.ini` + `alembic/` (`alembic init`). En `alembic/env.py` se cambiaron
  tres cosas respecto a la plantilla:
  1. `target_metadata = Base.metadata` importando `app.models` (sin ese import,
     `--autogenerate` no ve ninguna tabla).
  2. La URL sale de `settings.database_url`, no de `alembic.ini` (una sola fuente
     de verdad; la línea `sqlalchemy.url` del `.ini` queda inerte).
  3. `render_as_batch=True`: SQLite apenas soporta `ALTER TABLE`, así que Alembic
     emula los cambios recreando la tabla. Sin esto, la primera migración que
     toque una columna fallaría.
- `alembic/versions/4684c713e94f_fase1_library_folder_y_subtitle_file.py` —
  migración inicial: ambas tablas, FK con `ondelete=CASCADE`, índices únicos en
  `ruta` e índice en `estado` y `carpeta_id`.

**Tests** (`backend/tests/`, 48 casos)

- `conftest.py` — BD SQLite temporal por test (`tmp_path`), sesión, `TestClient`
  con `get_db` sobreescrito, y fixture `configurar_carpetas` (cambia
  `media_folders` e invalida el `cached_property` `carpetas`).
- `test_srt_parser.py` — parseo, conteo sin índices/tiempos, multilínea, BOM,
  fallback latin-1, malformado, y detección de idioma (10 casos parametrizados).
- `test_naming.py` — derivación del nombre bilingüe y su reconocimiento.
- `test_scanner.py` — escaneo inicial, sin cambios, fichero modificado, detección
  de traducido, vuelta a PENDING, huérfanos, borrado en cascada, ERROR, carpeta
  inexistente.
- `test_subtitles_api.py` — listado, filtros, 422 con filtro inválido, detalle,
  404 y `POST /scan`.

## Verificación realizada (2026-07-30)

- `uv run pytest` → **48 passed**.
- `uv run ruff check .` → limpio. `uv run ruff format .` aplicado (3 ficheros).
- `uv run alembic upgrade head` → tablas `library_folder`, `subtitle_file` y
  `alembic_version`.
- **E2E** contra `uvicorn` con una carpeta de prueba de 4 ficheros:
  - `POST /scan` → `{carpetas: 1, nuevos: 3, traducidos: 1, errores: 1, total: 3}`.
    El `.bilingue.srt` se excluye como fuente pero marca su original como
    `TRANSLATED`.
  - Segundo `POST /scan` → `sin_cambios: 3` (no reparsea).
  - `Roto.es.srt` → `ERROR` con el mensaje del parser, sin tumbar el escaneo.
  - `GET /subtitles` con filtros `?estado` e `?idioma`, detalle por id y 404: OK.

## Notas de entorno (histórico)

**Smart App Control (SAC)** bloqueó durante días el `python.exe` sin firmar de uv
(`os error 4551`), impidiendo ejecutar nada. Se desactivó y tras reiniciar quedó
`VerifiedAndReputablePolicyState = 0`. Resuelto; si reapareciera, comprobar:

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name VerifiedAndReputablePolicyState).VerifiedAndReputablePolicyState
```

## Pendiente al cerrar la fase

- **Commit de la Fase 1** (no se hace sin que el usuario lo pida).
- Crear `backend/.env` real con `MEDIA_FOLDERS` apuntando a las carpetas de Plex
  (el e2e se hizo con variables de entorno, sin escribir `.env`).
- Documentar el modelo de datos → `docs/modelo-datos.md`.
