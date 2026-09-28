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

## Hito 3 — Proveedor Azure Translator (2026-09-28)

### Qué se hizo

- **`services/translation/azure_provider.py`**: `TraductorAzure` sobre la API REST v3,
  con `httpx` (pasa a dependencia de ejecución).
  - Lotes que respetan a la vez los tres límites: 50 textos (el ritmo de la barra de
    progreso de la app), y los de Azure por petición, 1000 textos y 50.000
    caracteres.
  - Idiomas en minúscula (`es`, `en`, `ko`). La cabecera de región solo va si el
    recurso no es global.
  - **Reintentos propios** (aquí no hay SDK que los haga): hasta 5, ante `429` o
    `5xx` o un corte de red, con espera creciente (1, 2, 4, 8, 16 s) o la que pida
    Azure en `Retry-After`.
  - Errores: `401` → revisa la clave y la región; `403` → `CuotaAgotada`; un `429`
    que no cede → error de **ritmo**, no de cupo (el mes no está agotado).
  - **No implementa `consumo()`**: Azure no tiene API para consultarlo, así que su
    cupo sale del registro de la app.
- **Registro**: `azure` se crea solo con `AZURE_TRANSLATOR_KEY`; su límite es
  `AZURE_TRANSLATOR_LIMITE_MENSUAL`.

### Verificación

- 228 tests en verde (13 nuevos en `test_azure.py`, con `httpx.MockTransport` como
  servidor; ninguno llama a Azure): orden, idiomas y cabeceras, recurso global,
  lotes por número y por caracteres, vacíos, reintentos con `Retry-After` y con
  espera creciente, `429` persistente, `403`, `401`, respuesta incompleta y
  registro.
- **Prueba de humo real** con el recurso del usuario (plan F0, región `global`; la
  clave se configuró en `backend/.env` sin pasar por el chat), con las mismas tres
  frases de *Jaws* que en la Fase 3 (61 caracteres):

| Original | Azure | DeepL (Fase 3) |
|---|---|---|
| `- ¿Cómo era tu nombre?` / `- Chrissie.` | `- 이름이 뭐였어?` / `- 크리시.` | `- 이름이 뭐였지?` / `- 크리시.` |
| `No estoy borracho. ¡Espera!` | `나 안 취했어. 잠깐!` | `난 취하지 않았어. 잠깐만!` |

  La prueba reveló que **Azure deja un espacio antes de cada salto de línea** de los
  diálogos. El proveedor ahora quita los espacios al final de cada línea (test
  incluido; 229 en verde).
- **Elección con los dos proveedores reales**: Azure 0 usados de 2 M (registro),
  DeepL 61 de 1 M (API); una película media va a **Azure**, primero de la lista.
  Los 61 caracteres de la prueba no figuran en el registro de Azure porque los envió
  un script y no un trabajo de la app: es exactamente la limitación que la interfaz
  debe advertir.

## Hito 4 — Interfaz de cupos (2026-09-28)

### Qué se hizo

- **Backend**: `GET /translate/cupo` (Fase 3, un solo proveedor) **se retira**; todo
  usa `GET /translate/cupos`, para no tener dos fuentes de la misma cifra. Sus dos
  tests se quitan porque `test_consumo.py` ya cubre el endpoint nuevo. Los trabajos
  exponen `caracteres_previstos`.
- **`utils/cupos.ts`**: `nombreProveedor`, `libreTotal` y `repartir`, que
  **reproduce la regla de `eleccion.Asignador`** para que la interfaz diga de
  antemano qué proveedor traducirá cada obra. Es una previsión (decide el backend) y
  lo dice su comentario, que avisa de que hay que cambiarla si cambia la regla.
- **Cabecera**: el cupo libre total, con el desglose por proveedor al pasar el
  ratón; lleva a Trabajos.
- **Trabajos**: una tarjeta por proveedor, en orden de preferencia: libre, usados,
  reservados, límite, barra y **de dónde sale la cifra** («según DeepL» o «registro
  de la app, este mes; no ve lo gastado fuera de la app»). Proveedor en los trabajos
  en curso (con caracteres enviados de previstos) y en el historial.
- **Panel de detalle**: «Se traducirá con Azure · 44.388 caracteres», o «Sin cupo
  suficiente en ningún proveedor».
- **Panel de selección**: el proveedor previsto de cada obra, el cupo libre entre
  todos tras la selección y el aviso de las obras que no caben.
- Los textos que daban por hecho DeepL («Traducir con DeepL») pasan a genéricos.

### Verificación en el navegador

App real contra la copia de la BD y los proveedores reales del usuario (`azure,deepl`),
sin lanzar ninguna traducción:

| Pantalla | Resultado |
|---|---|
| `GET /translate/cupos` | Azure 0 de 2 M (registro) · DeepL 61 de 1 M (API) |
| Cabecera | «Cupo 2.999.939 libres» |
| Detalle de *Psycho* | «Se traducirá con Azure · 44.388 caracteres» |
| Selección (*Se7en*, *Pulp Fiction*, *Psycho*) | Psycho y Pulp Fiction → Azure; Se7en → fusión; 109.139 caracteres; 2.890.800 libres después |
| Trabajos | tarjetas de Azure (1.º) y DeepL (2.º) con la fuente de cada cifra |

Sin errores en consola. Backend: 227 tests en verde; frontend compila y el linter no
marca nada.

## Hito 5 y cierre de la fase (2026-09-28)

### Documentación

- `README.md` de la raíz: Azure y la elección por cupo en la descripción, tabla de
  variables del `.env` con las de Azure y `TRANSLATION_PROVIDERS` (y el aviso de que
  las claves van solo en ese fichero), y la Fase 4 marcada como hecha.
- `backend/README.md`: estructura de `services/translation/` y cómo se elige el
  proveedor.
- `CLAUDE.md`: stack, estructura, Fase 4 cerrada y tres puntos de deuda: el cupo de
  Azure por registro, la regla de elección duplicada en el frontend y la lección de
  PowerShell.

### Lo que deja la Fase 4

- **Dos proveedores**, Azure (preferido) y DeepL, probados con las cuentas reales.
- **Cupo libre total: ~3 M de caracteres**: 2 M/mes de Azure más lo que queda de 1 M
  de DeepL. Traducir la biblioteca entera son ~6 M, así que con el plan gratuito de
  Azure basta con unos tres meses.
- **Elección automática** con reserva de cupo, rechazo antes de empezar si no cabe y
  cambio de proveedor al reintentar si uno se agota.
- **La interfaz dice de dónde sale cada cifra** y qué proveedor traducirá cada obra.
- **227 tests** (196 al empezar la fase), ninguno llama a un proveedor real.

### Pendiente y a tener en cuenta

- **Mes de Azure**: se toma el natural. Si al revisar el portal de Azure el cupo se
  reinicia en otra fecha, habrá que ajustar `consumo._usados_este_mes`.
- **Calidad entre proveedores**: Azure y DeepL traducen parecido (ver la prueba de
  humo del hito 3), pero una película por cada uno en Plex lo confirmaría.
- **Repaso docente** (pendiente desde la Fase 3).
- **Fase 5 (MKV)** y el **despliegue con Docker**, en ese orden según el plan.
