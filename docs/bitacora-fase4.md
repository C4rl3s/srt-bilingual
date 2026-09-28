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
