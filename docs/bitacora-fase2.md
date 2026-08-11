# Bitácora — Fase 2 (Gestión de carpetas + vista de estado)

Registro de plan ↔ implementación de la Fase 2. Plan: `docs/plans/plan-fase2.md`.

## Estado: **COMPLETADA** (2026-08-11)

Código escrito, ejecutado y verificado. **79 tests en verde**, `ruff` y `oxlint`
limpios, `npm run build` (con `tsc`) correcto y flujo end-to-end comprobado contra
el servidor real. Pendiente únicamente el commit.

## Cambio de scope respecto al plan original

La Fase 2 estaba definida como "listado en React de traducidos vs. pendientes".
Al abordarla se decidió ampliarla: las carpetas dejan de configurarse en el `.env`
y pasan a gestionarse desde la interfaz. El listado se convierte en un **árbol** que
llega hasta el capítulo.

## Decisiones de diseño (tomadas con el usuario)

- **Dos árboles distintos.** El de *selección* (qué escanear) es plano: una fila de
  `library_folder` por carpeta raíz. El de *visualización* es profundo y se **deriva**
  de las rutas de `subtitle_file`. Persistir la jerarquía (con `padre_id`) se descartó:
  no aporta nada al escaneo —que ya es recursivo— y habría que mantenerla en sincronía
  con el disco.
- **La hoja es la obra, no el fichero.** Los `.srt` de un mismo capítulo en varios
  idiomas se agrupan por `base_sin_idioma`. Evita que un `.en.srt` aparezca como
  "pendiente" cuando el `.es.srt` de ese capítulo ya tiene su dual.
- **`MEDIA_FOLDERS` eliminado.** `library_folder` es la única autoridad.
- **La casilla se persiste** (`activa`). Desmarcar ≠ borrar: desmarcada no se
  re-escanea pero sus subtítulos siguen inventariados y visibles; borrarla se los
  lleva en cascada.
- **Sin solapamientos.** `POST /folders` rechaza con `409` una ruta que sea ancestro
  o descendiente de otra ya vigilada. Sin esa regla, dos carpetas encontrarían el
  mismo `.srt` y chocarían con el índice único de `subtitle_file.ruta`.
- **El explorador lo sirve el backend** (`/fs/*`): el navegador no puede dar la ruta
  absoluta de una carpeta del sistema.
- **Layout de una página, dos bloques**: carpetas arriba, árbol abajo.

## Implementado

**Backend**

- `app/config.py` — fuera `media_folders` y la `cached_property carpetas`.
- `app/models/library_folder.py` — columna `activa`; migración `bd028a52d162`
  (se crea con `server_default` para las filas existentes y se retira después).
- `app/api/folders.py` — `GET/POST /folders`, `PATCH/DELETE /folders/{id}`.
  El listado calcula los contadores con un `GROUP BY` y `count(...).filter(...)`.
- `app/api/filesystem.py` — `GET /fs/roots`, `GET /fs/browse`.
- `app/api/library.py` + `app/services/library_tree.py` — `GET /library/tree`.
- `app/services/scanner.py` — `escanear(db, carpeta_ids=None)`; ya no crea ni borra
  carpetas. `_escanear_carpeta`, `_procesar` y `_detectar_traducido` sin tocar.
- `app/services/subtitles/naming.py` — `_base_sin_idioma` promovida a pública.
- `app/schemas/` — `folder`, `filesystem`, `tree` y `PeticionEscaneo`.

**Frontend**

- `src/types.ts`, `src/api/client.ts` (envoltorio de `fetch` sobre `/api` + `ErrorApi`).
- `src/components/` — `PanelCarpetas`, `SelectorCarpeta` (modal de navegación),
  `ArbolSubtitulos` (render recursivo con plegado por nodo).
- `src/App.tsx` — compone los dos bloques, filtro por estado y refresco tras escanear.
- Borrados los assets sobrantes de la plantilla de Vite.

**Tests** — 79 casos (48 + 31 nuevos o adaptados)

- `conftest.py` — la fixture `configurar_carpetas` se sustituye por
  `registrar_carpetas`, que inserta filas en la BD.
- `test_folders_api.py`, `test_filesystem_api.py`, `test_library_tree.py` (nuevos).
- `test_scanner.py` — adaptado, + carpeta inactiva y escaneo selectivo.

## Verificación realizada (2026-08-11)

- `uv run pytest` → **79 passed**. `ruff check` / `format` limpios. `oxlint` limpio.
- `npm run build` (tsc + vite) correcto.
- `alembic upgrade head` desde cero aplica las dos migraciones en orden.
- **E2E** contra `uvicorn` con una biblioteca de prueba (una serie con dos capítulos,
  uno de ellos con `.bilingue.srt` y en dos idiomas, más un `.srt` malformado):
  - `/fs/roots` y `/fs/browse` navegan el disco.
  - Alta de la carpeta raíz OK; alta de una subcarpeta suya → `409`.
  - `POST /scan` → `{carpetas:1, nuevos:4, traducidos:1, errores:1, total:4}`.
  - `GET /library/tree` agrupa `BB.S01E01.es` + `.en` en una hoja marcada `DUAL`;
    filtrando por `TRANSLATED` se podan las ramas sin hojas.
  - Desmarcar → `POST /scan` recorre 0 carpetas y los 4 subtítulos siguen ahí.
  - Borrar el `.bilingue.srt` y re-escanear → la hoja vuelve a pendiente.
  - `DELETE /folders/{id}` → `204` y cascada limpia.

## Pendiente al cerrar la fase

- **Commit de la Fase 2.**
- Repaso docente `/teachpy` y `/teachreact` si el usuario lo pide.
