# Bitácora — Fase 4: cupos por proveedor y elección automática

Plan: `docs/plans/plan-fase4.md`. Esta bitácora recoge lo que acabó pasando, hito a
hito, con las decisiones tomadas por el camino y cómo se verificó.

## Decisiones previas (2026-09-28)

El usuario eligió **Azure Translator** como segundo proveedor, la **elección
automática por cupo** según su orden de preferencia, y que el cupo salga de **lo que
diga cada proveedor**. La documentación de Azure confirmó que no tiene API para
consultar el consumo, así que para Azure la cifra sale del registro de la app.

Al planificar se **descartó la tabla `provider_usage`** del plan original: el
consumo de un proveedor en un mes ya es la suma de `num_caracteres` de sus trabajos,
y una segunda tabla con la misma cifra podría descuadrarse.

## Hito 1 — Consumo por proveedor (2026-09-28)

### Qué se hizo

- **Configuración**: `TRANSLATION_PROVIDERS` (lista en orden de preferencia) y
  `Settings.proveedores`, que sigue aceptando el `TRANSLATION_PROVIDER` singular de
  la Fase 3. Variables de Azure: clave, región y `AZURE_TRANSLATOR_LIMITE_MENSUAL`
  (2 M por defecto, el cupo gratuito del plan F0).
- **`translation_job.caracteres_previstos`** (migración `4447e8a4d4c5`): lo que se
  espera enviar, fijado al crear el trabajo; 0 en las fusiones.
- **`services/translation/consumo.py`**: `estado(db, proveedor, …)` devuelve
  usados, reservados, límite, libre y la **fuente** de la cifra:
  - `API` si el proveedor implementa `ConCupo` (DeepL);
  - `REGISTRO` si no (Azure): la suma de lo enviado desde el día 1 del mes. Si la
    API de DeepL no responde, también se cae aquí, sin límite conocido.
  - **Reservados**: lo que falta por enviar de sus trabajos en cola o en curso.
  - Un proveedor sin clave o desconocido se informa igual, con su motivo.
- **`registry.limite_configurado`**: el límite de los proveedores que no lo informan.
- **`GET /translate/cupos`**: el estado de cada proveedor configurado, en su orden.
- `modelo-datos` al día; la tabla `provider_usage` figura como descartada.

### Verificación

- 205 tests en verde (9 nuevos en `test_consumo.py`): API contra registro, el
  registro solo cuenta el mes en curso y su proveedor, los fallidos cuentan, las
  reservas, un proveedor sin configurar, la caída de la API, el orden, la
  configuración y el endpoint. `ruff` limpio.
- Migración aplicada, deshecha y reaplicada; `alembic check` sin diferencias.
- **Contra la realidad** (`azure,deepl`): DeepL, según su API, **61 usados y 999.939
  libres**; Azure, no disponible, porque la app aún no lo conoce (hito 3).

## Hito 2 — Elección automática del proveedor (2026-09-28)

### Qué se hizo

- **`services/translation/eleccion.py`**: `Asignador` recibe los estados de cupo en
  orden de preferencia y, para cada traducción, devuelve el primer proveedor
  disponible con `libre ≥ previstos × 1,05`. Lleva la cuenta de lo que va
  asignando en la misma petición. Un límite desconocido (la API de DeepL caída) se
  da por bueno: si de verdad se agota, el reintento cambia de proveedor. `motivo()`
  explica el rechazo con lo libre de cada proveedor.
- **`trabajos.crear`** asigna el proveedor a cada traducción, salvo que se pida uno
  concreto. Si ninguno llega, la obra va a `rechazados` y **no se crea el
  trabajo**. El cupo se consulta **una sola vez por petición** y solo si hay algo
  que traducir: una fusión no cuesta ninguna llamada a DeepL.
- `POST /translate` pasa a la elección el mismo traductor que usa la tarea de fondo,
  así los tests inyectan proveedores falsos con cupos a medida.

### Protección: ningún test habla con un proveedor real

`settings` lee el `.env` de desarrollo, que tiene la clave real de DeepL. Con la
elección por cupo, un test podía acabar **consultando la cuenta real**. Se añadió en
`conftest.py` un fixture `autouse` que vacía las claves y la lista de proveedores en
todos los tests, y `cupo_de_sobra()` para los que crean trabajos sin ir de la
elección.

### Incidente: acentos corrompidos en un fichero de tests

Al preparar este hito salió a la luz que `tests/test_translate_api.py` tenía **todos
los caracteres no ASCII corrompidos** («aÃºn» en vez de «aún», y el coreano igual).
Lo causó en el hito 9 un reemplazo con `Get-Content … | Set-Content` de PowerShell
5.1, que leyó el fichero UTF-8 como Windows-1252 y lo reescribió así. Los tests
seguían pasando porque las cadenas coreanas se corrompieron igual donde se escriben
y donde se comprueban, y el fichero llegó así al commit `30e294f`.

Se reparó deshaciendo la conversión (volver a los bytes originales y leerlos como
UTF-8), y se revisaron todos los `.py`, `.ts`, `.tsx` y `.md` del repo: no había
ningún otro afectado. **Lección**: para reescribir ficheros desde PowerShell, usar
`[IO.File]::ReadAllText` / `WriteAllText` con UTF-8 explícito, o el editor, nunca
`Get-Content | Set-Content`.

### Verificación

- 215 tests en verde (10 nuevos en `test_eleccion.py`): orden, salto al siguiente,
  margen, reservas en la misma petición, no disponibles, límite desconocido,
  rechazo con motivo, reparto de una petición entre dos proveedores por la API,
  rechazo sin crear trabajo y **reintento tras agotarse** que elige otro proveedor.
- **Con los proveedores reales** (`azure,deepl`, sin crear trabajos): una película
  media (34.304 caracteres) → DeepL; la biblioteca entera (6 M) → rechazada con
  «azure: proveedor desconocido; deepl: 965.635 libres».
