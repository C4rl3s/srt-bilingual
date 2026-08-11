# Fase 2 (scope ampliado) — Gestión de carpetas desde la interfaz + árbol de estado

## Contexto

La Fase 1 dejó las carpetas a escanear declaradas en `MEDIA_FOLDERS` del `.env`, y
el scanner **borra** de la base de datos toda carpeta que no esté en esa variable
(`scanner.py:41-45`). Eso obliga a editar un fichero y reiniciar el backend cada vez
que quieres vigilar una biblioteca nueva.

El objetivo es que las carpetas se gestionen **desde la interfaz**: navegar el disco,
seleccionar una carpeta, añadirla, marcar con casillas cuáles entran en el próximo
escaneo, y ver el resultado como un **árbol que llega hasta el capítulo**, indicando
para cada obra qué idiomas tiene y si existe ya su versión dual. La Fase 2 original
(listado de traducidos vs. pendientes) queda absorbida: el árbol *es* el listado.

Decisiones tomadas al planificar:

1. **Dos árboles distintos.** `library_folder` guarda **solo las raíces** que añades.
   El árbol profundo que se muestra se **deriva** de las rutas ya guardadas en
   `subtitle_file` — sin `padre_id`, sin jerarquía persistida, y se autocorrige al
   renombrar carpetas en disco.
2. **La hoja es la obra**, no el fichero: los `.srt` del mismo capítulo se agrupan
   por su nombre base y la hoja resume idiomas disponibles + si hay dual.
3. **`MEDIA_FOLDERS` desaparece.** La tabla pasa a ser la única autoridad.
4. **La casilla se persiste** en una columna `activa`. Semántica: desmarcar = "no la
   re-escanees" (sus subtítulos siguen en la BD y visibles); borrar = fuera ella y
   sus subtítulos, en cascada.
5. **Layout:** una sola página con dos bloques (carpetas arriba, árbol abajo).

---

## Qué de la Fase 1 queda afectado

Conviene tenerlo claro antes de empezar: esto **modifica** código ya commiteado
(`4ebbc0f`), no solo añade.

| Fichero | Qué le pasa |
|---|---|
| `app/config.py` | Pierde `media_folders` y la `cached_property carpetas` |
| `app/services/scanner.py:39-55` | Fuera la reconciliación contra el `.env`; las carpetas ya no se crean ni se borran aquí |
| `app/models/library_folder.py` | +1 columna `activa` |
| `tests/conftest.py:66-82` | La fixture `configurar_carpetas` deja de tener sentido (dependía de `settings.media_folders`) |
| `tests/test_scanner.py` | Todos los casos que usan esa fixture |
| `backend/.env.example` | Fuera el bloque `MEDIA_FOLDERS` |

**No se toca:** `srt_parser.py`, `modelo.py`, `db.py`, `alembic/env.py`,
`models/subtitle_file.py`, `schemas/subtitle.py`, `api/subtitles.py`. De `naming.py`
solo se promueve `_base_sin_idioma` a pública.

---

## Paso 0 — Documentación (antes de tocar código)

> **Nota de orden.** `docs/modelo-datos.md:4-5` se impone la regla de actualizarse
> *en el mismo commit que la migración*. Por eso aquí se actualizan solo `CLAUDE.md`
> y `README.md` (plan y uso); los cambios de `modelo-datos.md` / `.html` quedan
> descritos abajo pero se aplican junto con la migración. Si prefieres hacerlo todo
> de una vez, se hace y ya está.

### 0.1 — Los planes se mudan al repo

Crear `docs/plans/` y poblarla:

- `docs/plans/plan-fase2.md` — este plan.
- `docs/plans/plan-fase1.md` — copia del contenido de
  `~/.claude/plans/reactive-floating-token.md` (el plan de cierre de la Fase 1,
  del 2026-07-30).

Después, **borrar los dos ficheros de `~/.claude/plans`** (`reactive-floating-token.md`
y `vale-pues-vamos-a-atomic-rainbow.md`), que quedan como borradores ya trasladados.

Añadir además una línea al párrafo de **Documentación** de `CLAUDE.md:211-213`
señalando que los planes de cada fase viven en `docs/plans/plan-faseN.md`, en
paralelo a las bitácoras.

### 0.2 — Directriz global (`C:\Users\Beicon\.claude\CLAUDE.md`)

Sección nueva, para que aplique a todos los proyectos:

```markdown
## Planes de desarrollo: dónde se guardan

- Si trabajamos **dentro de un proyecto con carpeta propia**, el plan definitivo va
  **al repo**, en `docs/plans/plan-<fase-o-tema>.md`, versionado con el resto de la
  documentación y con nombre descriptivo (nada de slugs aleatorios).
- Si **no** hay proyecto definido (consultas sueltas, exploraciones), el plan se
  queda en la carpeta global `~/.claude/plans` para que no se pierda.
- El fichero que crea el modo plan en `~/.claude/plans` es un **borrador de
  trabajo**: cuando el plan se da por bueno, se traslada al repo y se borra el
  borrador, de modo que exista una sola fuente de verdad.
```

### 0.3 — `CLAUDE.md` del proyecto

**a) Línea 196** — corregir lo que quedó obsoleto tras el commit de ayer:
`*(Sin commitear aún.)*` → `Commit \`4ebbc0f\`.`

**b) Líneas 197-198** — sustituir el bullet de la Fase 2 por:

```markdown
- [ ] **Fase 2 — Gestión de carpetas + vista de estado.** Alta y baja de carpetas
  desde la interfaz (explorador de disco servido por el backend), casilla por
  carpeta para elegir cuáles entran en el escaneo (columna `activa`, persistida) y
  botón de "Escanear". El resultado se muestra como un **árbol derivado de las
  rutas** que llega hasta la obra (capítulo/película), con los idiomas disponibles
  y si ya existe su versión dual. `MEDIA_FOLDERS` desaparece: `library_folder` pasa
  a ser la única autoridad sobre qué se vigila.
```

**c) Bloque de arquitectura (líneas 50-72)** — añadir los módulos nuevos:
`schemas/` gana `folder`, `tree`; `api/` gana `folders`, `filesystem`, `library`;
`services/` gana `library_tree.py`; y el frontend pasa de `src/App.tsx` a
`src/{api/client.ts, types.ts, components/}`.

### 0.4 — `README.md`

- **Línea 39** — `cp .env.example .env  # y edita MEDIA_FOLDERS con tus carpetas`
  pasa a `cp .env.example .env  # opcional (idioma destino, clave de DeepL)`, y se
  añade después: *"Las carpetas a vigilar se añaden desde la interfaz, no aquí."*
- **Tabla de endpoints (líneas 50-54)** — añadir `GET/POST /folders`,
  `PATCH/DELETE /folders/{id}`, `GET /fs/roots`, `GET /fs/browse`,
  `GET /library/tree`; y matizar que `POST /scan` recorre las carpetas marcadas.
- **Aviso de seguridad** (nuevo, junto a la puesta en marcha del backend): `/fs/browse`
  lista directorios de la máquina, así que uvicorn debe escuchar en `127.0.0.1`
  (el valor por defecto), nunca en `0.0.0.0`.
- **Líneas 77-78** — marcar Fase 1 como hecha con su commit y reescribir la Fase 2
  en una línea coherente con el bullet de `CLAUDE.md`.

### 0.5 — `docs/modelo-datos.md` (+ `.html`, mismos puntos) — con la migración

1. **Línea 3-4** — "Refleja la migración `4684c713e94f` (Fase 1)" pasa a nombrar
   también la revisión nueva.
2. **Diagrama Mermaid (línea 30-36)** — añadir `bool activa "entra en el escaneo"`.
3. **Líneas 61-63** — deja de ser "espejo de `MEDIA_FOLDERS`". Nueva redacción:
   catálogo de carpetas que gestiona el usuario desde la interfaz; existe para
   colgar de ella los subtítulos, recordar si entra en el escaneo y registrar
   cuándo se escaneó.
4. **Tabla de columnas** — fila nueva: `activa` / `BOOLEAN` / no / *Si entra en el
   próximo escaneo. Desmarcarla no borra nada: sus subtítulos siguen inventariados*.
5. **Líneas 75-76** — las carpetas ya no se reconcilian contra el `.env`: se dan de
   alta y de baja por API, con rechazo de solapamientos.
6. **Decisión nº5 (líneas 161-164)** — reescribir. Sigue sin haber baja lógica *de
   datos* (borrar una carpeta borra sus filas en cascada), pero ahora existe una
   bandera de **inclusión en escaneo**, que es otra cosa. Documentar la distinción
   entre desmarcar y borrar, y añadir la restricción de no solapamiento y su motivo
   (el índice único de `subtitle_file.ruta`).

El `.html` es autocontenido y hay que editarlo a mano en los bloques equivalentes
(entidad `library_folder` ~527-576, índices ~755-770, decisión nº5 ~874-880).

---

## Backend

### 1. Configuración — `app/config.py`

Eliminar el campo `media_folders` y la `cached_property carpetas`. `Settings` se
queda con `database_url`, `default_target_lang` y `deepl_api_key`.

### 2. Modelo — `app/models/library_folder.py`

```python
activa: Mapped[bool] = mapped_column(Boolean, default=True)
```

Migración con `alembic revision --autogenerate -m "carpeta activa"`, revisando lo
generado. `render_as_batch=True` ya está en `alembic/env.py`, así que el `ALTER
TABLE` sobre SQLite se resuelve solo. Al ser columna no-nula sobre filas existentes,
la migración necesita `server_default=sa.true()`.

### 3. Explorador de disco — `app/api/filesystem.py` (nuevo)

Hace falta porque el navegador **no puede** dar la ruta absoluta de una carpeta
(`<input type="file" webkitdirectory>` solo devuelve rutas relativas):

- `GET /fs/roots` → unidades. En Windows probar `A:`–`Z:` con `Path(f"{l}:\\").exists()`.
- `GET /fs/browse?ruta=<abs>` → `{ruta, padre, directorios: [{nombre, ruta}]}`.
  Solo directorios, resueltos con `Path.resolve()`, ordenados, saltando ocultos y
  capturando `PermissionError` por entrada para que una carpeta protegida no tumbe
  el listado. 404 si no existe o no es directorio.

### 4. CRUD de carpetas — `app/api/folders.py` + `app/schemas/folder.py` (nuevos)

- `GET /folders` → `id`, `ruta`, `activa`, `ultimo_escaneo` y contadores agregados
  (`num_subtitulos`, `num_dual`, `num_pendientes`) con `func.count`.
- `POST /folders` `{ruta}` → 400 si no existe o no es directorio; resuelve con
  `Path.resolve()`; **409 si solapa** con una ya registrada (ancestro o
  descendiente, comprobado con `Path.is_relative_to` en ambos sentidos) o si está
  duplicada. El solapamiento es lo que impide que dos carpetas encuentren el mismo
  `.srt` y choquen contra el índice único de `subtitle_file.ruta`.
- `PATCH /folders/{id}` `{activa}` → marca/desmarca.
- `DELETE /folders/{id}` → borra; la cascada ya existente se lleva sus subtítulos.

### 5. Scanner — `app/services/scanner.py`

`_escanear_carpeta`, `_procesar` y `_detectar_traducido` **no se tocan**.

En `escanear(db, carpeta_ids: list[int] | None = None)`:
- Eliminar la reconciliación contra `settings.carpetas` (líneas 39-55).
- Recorrer las carpetas de `carpeta_ids` si viene; si no, las que tengan `activa`.
- Mantener huérfanos, `ultimo_escaneo` y `ResumenEscaneo` igual.

`app/schemas/scan.py`: `PeticionEscaneo(carpeta_ids: list[int] | None = None)`.
`app/api/scan.py`: aceptar ese cuerpo como opcional.

### 6. Árbol derivado — `app/services/library_tree.py` + `app/schemas/tree.py` (nuevos)

`construir_arbol(db, carpeta_ids=None, estado=None) -> list[NodoArbol]`:

1. Cargar los `ArchivoSubtitulo` de las carpetas pedidas.
2. Ruta relativa a la raíz de su carpeta (`Path(sub.ruta).relative_to(carpeta.ruta)`),
   partida en segmentos.
3. Segmentos intermedios = nodos de directorio; el último nivel agrupa por **obra**:
   clave `(directorio, base_sin_idioma(nombre))`.
4. Agregados por nodo: nº de obras, nº con dual, nº en error.

Reutilizar `_base_sin_idioma` (`naming.py:18`) **promoviéndola a pública**
(`base_sin_idioma`); ya hace justo eso (`Pelicula.es.srt` → `Pelicula`) y
`derivar_nombre_bilingue` la sigue usando.

`NodoArbol` es un modelo Pydantic recursivo (`hijos: list["NodoArbol"]`, soportado
de forma nativa en v2). En las hojas: `idiomas: list[Idioma]`, `dual: bool`,
`ruta_bilingue: str | None`, `num_caracteres`, y `subtitulo_ids: list[int]` (harán
falta en Fase 3 para lanzar la traducción desde el árbol).

Endpoint `GET /library/tree` con `?carpeta_id=` y `?estado=`; al filtrar, podar las
ramas que se quedan sin hojas. `GET /subtitles` y `/subtitles/{id}` se mantienen.

### 7. `app/main.py`

Incluir los routers `filesystem`, `folders` y `library`.

---

## Frontend

Sin router ni librería de estado: una página, dos bloques, `fetch` + hooks.

- `src/api/client.ts` — envoltorio de `fetch` sobre `/api/...` (nunca
  `localhost:8000`) que lanza en respuestas no-OK y tipa el JSON.
- `src/types.ts` — espejo TS de los DTOs.
- `src/components/PanelCarpetas.tsx` — carpetas con casilla, contadores,
  `ultimo_escaneo`, papelera, "+ Añadir" y "Escanear".
- `src/components/SelectorCarpeta.tsx` — modal de navegación (unidades,
  subdirectorios, migas de pan, subir un nivel, "Seleccionar esta carpeta").
- `src/components/ArbolSubtitulos.tsx` + `NodoArbol.tsx` — render recursivo con
  expandir/contraer y badges de estado en las hojas.
- `src/App.tsx` — compone los dos bloques y refresca el árbol tras escanear.

De paso se pueden borrar los assets sobrantes de la plantilla (`hero.png`,
`react.svg`, `vite.svg`, `public/icons.svg`), ya anotados como deuda.

---

## Tests

- `tests/conftest.py` — eliminar `configurar_carpetas` y sustituirla por una fixture
  que inserte filas `CarpetaBiblioteca` en la BD de test.
- `tests/test_scanner.py` — adaptar los casos existentes; añadir uno de carpeta con
  `activa=False` (no se escanea) y otro de escaneo selectivo por `carpeta_ids`.
- `tests/test_folders_api.py` (nuevo) — alta, ruta inexistente (400), duplicado (409),
  solapamiento ancestro/descendiente (409), toggle, borrado en cascada.
- `tests/test_filesystem_api.py` (nuevo) — `roots`, `browse` sobre `tmp_path`, 404,
  y que no liste ficheros.
- `tests/test_library_tree.py` (nuevo) — agrupación por obra (`.es` + `.en` del mismo
  capítulo = una hoja), varios niveles de profundidad, agregados de dual, podado al
  filtrar.

---

## Verificación

```powershell
cd backend
uv run alembic upgrade head          # aplica la columna `activa`
uv run pytest                        # los 48 adaptados + los nuevos
uv run ruff check . ; uv run ruff format .
uv run uvicorn app.main:app --reload --port 8000

cd ../frontend
npm run build                        # type-check con tsc
npm run dev
```

End-to-end en el navegador, con una carpeta que replique el caso real (una serie,
una temporada, varios capítulos, uno con su `.bilingue.srt`):

1. "+ Añadir" → navegar → seleccionar → aparece en el panel.
2. Intentar añadir una subcarpeta suya → 409 con mensaje claro.
3. Marcar y "Escanear" → el resumen cuadra y el árbol llega al capítulo, con el
   que tiene dual en verde y el resto pendiente.
4. Recargar sin escanear → árbol y casillas intactos (persistencia).
5. Desmarcar y escanear → no se recorre, pero sigue visible.
6. Borrar la carpeta → desaparece ella y sus subtítulos.
7. Borrar a mano un `.bilingue.srt` y re-escanear → esa hoja vuelve a pendiente.
