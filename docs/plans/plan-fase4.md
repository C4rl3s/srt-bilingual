# Fase 4 — Cupos por proveedor y elección automática

## Contexto

El plan original de esta fase era una tabla `provider_usage` (proveedor, mes,
caracteres, cuota) y elegir el proveedor según su cupo libre del mes. Dos cosas de
la Fase 3 lo cambian:

1. **DeepL ya no da una API gratuita mensual.** Desde julio de 2026 solo ofrece
   planes con cupo total o de pago. La cuenta del usuario tiene **1 M de caracteres
   en total**, y traducir la biblioteca son **~6 M** (162 películas, mediana de
   34.000 caracteres).
2. **Ya existe el libro de cuentas.** Cada `translation_job` guarda su proveedor y
   los caracteres enviados, que cuentan aunque el trabajo falle. Una tabla aparte
   duplicaría ese dato.

Decisiones del usuario (2026-09-28):

- **Segundo proveedor: Azure Translator**, con plan gratuito F0.
- **Elección automática por cupo**: el primero de su lista de preferencia que tenga
  cupo suficiente para la obra; al agotarse uno, el siguiente.
- **El cupo lo dice el proveedor** siempre que pueda; si no, el registro propio de
  la app.

## Lo que se sabe de Azure (documentación oficial, 2026-09-28)

| Aspecto | Dato |
|---|---|
| Endpoint | `POST https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=es&to=ko` |
| Autenticación | cabeceras `Ocp-Apim-Subscription-Key` y `Ocp-Apim-Subscription-Region` |
| Cuerpo | `[{"Text": "..."}, …]`; la respuesta mantiene el orden |
| Límite por petición | 1000 textos y 50.000 caracteres |
| Ritmo del plan F0 | 2 M de caracteres por **hora**, en ventana deslizante (~33.000 por minuto) |
| Cupo gratuito del plan F0 | 2 M de caracteres al **mes** (página de precios) |
| Consumo | **no hay API para consultarlo**; cada respuesta trae `X-metered-usage` con lo facturado en esa petición |
| Errores | `401` clave mala · `403` cupo gratuito agotado · `429` demasiado deprisa |

Consecuencia: para Azure, el cupo sale del **registro propio** (lo enviado este mes
según `translation_job`). No verá lo que se gaste con esa clave fuera de la app; en
la interfaz se indica de dónde sale cada cifra.

## Alcance

**Dentro:**

1. Consumo por proveedor: lo que dice su API (`ConCupo`) o el registro propio del
   mes, más lo **reservado** por trabajos en cola o en curso.
2. Configuración de varios proveedores con orden de preferencia y límite.
3. **Elección automática** del proveedor al crear cada trabajo de traducción.
4. Proveedor **Azure Translator**.
5. Interfaz: el cupo de cada proveedor y de dónde sale, el proveedor elegido en cada
   trabajo y el cupo total en la cabecera.

**Fuera:**

- Proveedores de pago o con LLM, y Google (se añadiría igual que Azure).
- Repartir una misma película entre dos proveedores: cada trabajo usa uno solo.
- La tabla `provider_usage` del plan original (ver Diseño, punto 1).

## Diseño

### 1. Sin tabla nueva: `translation_job` es el registro

El consumo propio de un proveedor en un periodo es la suma de `num_caracteres` de sus
trabajos en ese periodo. Es la misma cifra que guardaría `provider_usage`, sin el
riesgo de que las dos se desincronicen.

Sí se añade **una columna**, `translation_job.caracteres_previstos`: lo que se espera
enviar, fijado al crear el trabajo (los `num_caracteres` del origen). Sirve para
**reservar** cupo mientras el trabajo está en cola, y para la barra de progreso en
caracteres.

### 2. Configuración

En el `.env`:

```
TRANSLATION_PROVIDERS=azure,deepl        # orden de preferencia
AZURE_TRANSLATOR_KEY=...
AZURE_TRANSLATOR_REGION=westeurope
AZURE_TRANSLATOR_LIMITE_MENSUAL=2000000  # el cupo gratuito del plan F0
DEEPL_API_KEY=...                        # su límite lo informa su API
```

`TRANSLATION_PROVIDER` (singular, Fase 3) se sigue aceptando como lista de uno.

### 3. Consumo por proveedor

Nuevo `services/translation/consumo.py`:

```
estado_cupo(nombre) -> EstadoCupo(proveedor, usados, reservados, limite, periodo, fuente)
```

- `fuente = "API"` si el proveedor implementa `ConCupo` (DeepL); si no, `"REGISTRO"`
  (Azure): suma de `num_caracteres` de sus trabajos desde el día 1 del mes (UTC).
- `reservados`: `caracteres_previstos − num_caracteres` de sus trabajos en cola o en
  curso.
- `libre = limite − usados − reservados`.

**Aviso**: el periodo de Azure se toma como mes natural. Si Azure reinicia el cupo en
otra fecha (el aniversario de la suscripción), el registro propio se desviará unos
días. Se comprobará con el portal de Azure en la prueba real.

### 4. Elección automática

En `trabajos.crear`, para cada traducción sin proveedor forzado:

1. Recorre `TRANSLATION_PROVIDERS` en orden.
2. Elige el primero con `libre ≥ caracteres_previstos × 1,05` (margen del 5 %: cada
   proveedor cuenta los caracteres a su manera).
3. Las reservas de la misma petición se van sumando: si se piden 20 películas, no se
   asignan todas al mismo proveedor aunque cada una quepa por separado.
4. Si ninguno llega, la obra va a `rechazados` con el motivo («Sin cupo suficiente:
   DeepL 12.000 libres, Azure 8.500»), y **no se crea el trabajo**.

Si un proveedor se agota a mitad (`CuotaAgotada`), el trabajo falla como hoy y
**Reintentar** vuelve a pasar por la elección, que ya no lo escogerá.

### 5. Proveedor Azure

Nuevo `services/translation/azure_provider.py`, con `httpx` (dependencia de
runtime):

- Lotes por el menor de los tres límites: 50 textos (el de la app), 1000 textos y
  50.000 caracteres (los de Azure).
- Idiomas en minúscula (`es`, `en`, `ko`).
- `401` → `ErrorTraduccion` (revisa la clave) · `403` → `CuotaAgotada` · `429` y
  `5xx` → reintentos con espera creciente, porque aquí no hay SDK que los haga,
  como sí pasa con DeepL.
- Verifica la invariante de un texto por texto, como DeepL.

### 6. API

| Endpoint | Cambio |
|---|---|
| `GET /translate/cupos` | **Nuevo**: el estado de cada proveedor configurado, en orden de preferencia |
| `GET /translate/cupo` | ~~Se mantiene (cabecera)~~ **Retirado en el hito 4**: la cabecera suma los de `/translate/cupos`, y así no hay dos fuentes de la misma cifra |
| `POST /translate` | Asigna el proveedor según cupo; nuevos motivos de rechazo |

### 7. Frontend

- **Trabajos**, columna lateral: una tarjeta por proveedor, en su orden de
  preferencia, con libre, usados, reservados, límite, periodo y **de dónde sale la
  cifra** («según DeepL» o «registro de la app»).
- **Cabecera**: cupo libre total.
- **Trabajos e historial**: el proveedor de cada trabajo.
- **Selección múltiple**: el cupo libre total, y el aviso si no alcanza.

## Orden de trabajo

| Hito | Contenido | Verificable por |
|---|---|---|
| **1** | `caracteres_previstos` (migración), `consumo.py`, configuración de varios proveedores y `GET /translate/cupos` | Tests con proveedores falsos |
| **2** | Elección automática en `trabajos.crear` | Tests: orden, margen, reservas en la misma petición, sin cupo, reintento tras agotarse |
| **3** | Proveedor Azure | Tests con `httpx.MockTransport`; prueba de humo real con la clave del usuario |
| **4** | Frontend | Recorrido en el navegador |
| **5** | Documentación: bitácora, modelo de datos, READMEs | — |

Los hitos 1, 2 y 4 no necesitan la cuenta de Azure: se prueban con proveedores
falsos y con DeepL. **El hito 3 necesita que el usuario cree antes el recurso
Translator en Azure** (plan F0) y ponga la clave y la región en el `.env`.

## Riesgos

1. **Cupo de Azure invisible fuera de la app**: el registro propio no ve lo gastado
   con la clave en otro sitio. Se avisa en la interfaz.
2. **Mes de Azure distinto del natural**: ver el aviso del Diseño, punto 3.
3. **Ritmo del plan F0**: una película son ~35.000 caracteres y el límite son ~33.000
   por minuto. Una traducción seguida puede chocar con él: de ahí los reintentos
   con espera ante `429`.
4. **Calidad distinta entre proveedores**: una película traducida por Azure y otra
   por DeepL pueden sonar distinto. Se verá en Plex en la prueba real.
