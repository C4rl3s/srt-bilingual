# Bitácora — Fase 5: subtítulos incrustados en MKV

Plan: `docs/plans/plan-fase5.md`. Decisiones del usuario (2026-09-28):

- El bilingüe sale siempre como `.srt` **fuera del MKV**; no se inyecta nada.
- Dos casos: traducir una pista, y fusionar una pista ES/EN con un coreano (otra
  pista del mismo MKV o un `.srt` externo).
- **Sin OCR** en esta fase: los 130 capítulos de Series que solo traen el
  español/inglés como imagen (PGS) quedan como no elegibles, con motivo `IMAGEN`.
- **Castellano antes que latino** entre dos españoles.

## Hito 1 — Sondeo de pistas en segundo plano (2026-09-28)

### Qué se hizo

- **Modelo** (migración `c3a9e5f17b20`): una pista incrustada es una fila de
  `subtitle_file` con `video_id` (cascada con su vídeo), `indice_pista`,
  `titulo_pista`, `metricas_exactas` y `ruta_extraida`; `formato` admite los códecs de
  las pistas; `media_file.sondeado_mtime` marca con qué `mtime` se sondeó cada vídeo.
- **`services/mkv/sondeo.py`**: `ffprobe` de la cabecera, `leer_pistas` (función
  pura sobre su JSON), `reconciliar` (las pistas se identifican por índice y
  conservan su fila al volver a sondear) y `sondear_pendientes`, la tarea de fondo.
  `POST /scan` sigue siendo el inventario rápido y deja el sondeo en cola;
  `GET /scan/sondeo` informa del progreso.
- Solo se guardan las pistas ES/EN/KO y las que no declaran idioma: un MKV de Netflix
  trae 33 y guardarlas todas llenaría de ruido el panel de candidatos. Hay que
  distinguir «sin etiqueta» (`und`: el contenido aún puede decidir) de «declara un
  idioma que la app no conoce» (`ara`, `pol`: se descarta). El primer intento las
  confundía y guardaba 25 pistas de *Moonrise*.
- Forzado y SDH salen del **título** (`Forced`, `FORZADOS`, `[Signs]`, `SDH`,
  `[CC]`) y de la marca `hearing_impaired`. **La marca `forced` se ignora.**
- **Selección** (`seleccion.py`):
  - motivo nuevo `IMAGEN`;
  - castellano antes que latino (`Latin`, `LAT`, `América`, `419` en el título o el
    nombre);
  - un `.srt` antes que una pista del mismo idioma (se lee al momento);
  - el coreano de la misma procedencia que el origen: si el origen es una pista, la
    coreana del mismo MKV, que en los de Netflix comparte los tiempos al milisegundo;
  - una pista sin estadísticas (0 líneas = no se sabe) no se descarta por pequeña.
- Lo que aún no sabe leer una pista se protege: el renombrado para Plex las ignora,
  `POST /translate` las rechaza con un motivo claro («aún no se pueden generar», hasta
  el hito 3) y los candidatos no dan muestra ni calidad de fusión sin extraer.
- **Tests**: fixtures con salidas **reales** de `ffprobe` (*Moonrise*, *Shingeki*,
  *Jujutsu Kaisen*, *Better Call Saul*, *Agáchate, maldito*). El `client` de los
  tests usa un `ffprobe` de pega y sesiones contra la BD de pruebas: sin eso, un
  `POST /scan` de test habría abierto la base de datos de desarrollo desde la tarea
  de fondo.

### El hallazgo: las líneas de la cabecera no se comparan

Primera pasada real por Anime: 207 obras elegibles, pero **57 con origen inglés**
aunque todas tienen pista española. En *Jujutsu Kaisen* 01, la pista inglesa
(fansub) declara 1023 líneas y la española 390: los carteles y el karaoke de las
canciones se trocean en decenas de eventos ASS. La regla de la Fase 3 (menos del
40 % del más largo = forzado encubierto) descartaba el español completo.

Arreglo: la proporción solo se aplica con **cifras exactas**; con las de la cabecera,
solo el mínimo absoluto de 100 líneas. Queda un test con el caso real.

### Verificación

- `uv run pytest` → **250 passed** (227 al empezar la fase). `ruff` limpio.
- Migración sobre una copia de la BD de desarrollo: `upgrade`, `alembic check` sin
  diferencias, `downgrade -1` y `upgrade` otra vez.
- **Contra la biblioteca real** (Anime, con el backend sobre la copia):
  - `POST /scan` → **2 s**; el sondeo de los 215 vídeos, en segundo plano:
    **6 min, 0 errores**.
  - Árbol: **207 obras elegibles** (206 con origen español, 1 inglés: *Rooster
    Fighter*, que no trae español) y **27 con coreano para fusionar**, las mismas
    cifras que el sondeo previo. Las 8 sin subtítulos son las aperturas y cierres
    sin créditos de *Jujutsu Kaisen*.
  - *Moonrise* 01: origen pista 7 `NF_Spanish` (no la latina de 297 líneas),
    coreano pista 25 del mismo MKV. *Jujutsu Kaisen* 01: la pista 9 castellana, no la
    6 latina.

Commit `55e5ef6`.

## Hito 2 — Parser ASS, extracción y caché (2026-09-28)

### Qué se hizo

- **`subtitles/ass_parser.py`**: lee el ASS directamente (la conversión de ffmpeg a
  SRT mete `<font>` en cada línea) y se queda solo con el diálogo: fuera las
  etiquetas `{\...}`, los carteles (por estilo, o por `\pos`/`\move`), los dibujos
  (`\p1`), el karaoke (`\k`) y los estilos de opening/ending; las capas repetidas
  del mismo texto quedan una vez; ordenado por inicio.
- **`subtitles/lectura.py`**: `leer_bloques(sub)`, el único punto por el que se lee
  un subtítulo, sea `.srt` o pista extraída (ASS o SRT según su códec).
  `PistaSinExtraer` si la pista aún no está en la caché.
- **`mkv/extraccion.py`**: **una sola pasada de ffmpeg por vídeo** saca todas sus
  pistas de texto a `CACHE_DIR/pistas/<video_id>/`. Se escribe a `.part` y se
  renombra al acabar, para que un corte no deje una pista truncada que parezca
  buena. Tras extraer, métricas **exactas** e idioma por contenido. Un cerrojo por
  vídeo evita leerlo dos veces si coinciden un trabajo y el botón. La caché se
  borra si el vídeo cambia (al volver a sondearlo) o desaparece (escaneo).
- **API**: `POST /videos/{id}/extraer` (`202`, en segundo plano). Los candidatos
  dicen si falta extraer (`extraccion_pendiente`, `video_id`, `extrayendo`,
  `error_extraccion`) y, con las pistas extraídas, dan muestra y calidad de fusión.

### Calibración del filtro con ASS reales de fansub

Extraídas las pistas de *Jujutsu Kaisen* 01 (**249 s**: rip de BD con FLAC) y
*Kaiju No. 8* S02E00 (**36 s**):

| Pista | Eventos | Diálogo | Qué salió |
|---|---|---|---|
| *Jujutsu* inglés | 1023 | **393** | 469 carteles (`Signs`), 88 dibujos del opening (`OP1`), 73 rótulos (`Sign2`) |
| *Jujutsu* español | 390 | **364** | 26 carteles `Cart_A_Tre`/`Cart_C_Tre` |
| *Kaiju* inglés | 369 | **347** | 22 carteles `sign_…` |
| *Kaiju* español | 343 | **331** | 12 carteles `Cart_…` |
| *Kaiju* `English[Signs]` | 20 | **0** | todo carteles: tras extraerla, se descarta sola |
| *Shingeki* español | 287 | **279** | `Sign_Default*`, `EndCard` |
| *Moonrise* español (Netflix) | 292 | **292** | nada: es todo diálogo |

Tras el filtro, las cifras de las pistas de una misma obra ya son comparables (393
frente a 364 en *Jujutsu*, frente a 1023 y 390 antes). El estilo `Cart_` del fansub
español no estaba en la primera versión: se vio aquí y se añadió.

### Verificación

- `uv run pytest` → **288 passed**. `ruff` limpio; el frontend compila.
- **Contra la biblioteca real**, con el backend sobre la copia de la BD: `POST
  /videos/22/extraer` sobre *Moonrise* 01 → las 5 pistas en **120 s**, métricas
  exactas, y en los candidatos **calidad de fusión 1,0** con muestra correcta
  («Aunque… de pequeño la escuchaba un montón» / «근데 어릴 때 자주 들은
  노래거든»).

Commit `96c2bb6`.

## Hito 3 — Trabajos desde pistas (2026-09-28)

### Qué se hizo

- `trabajos.crear` acepta pistas. Los tres casos del usuario salen de la selección
  sin código aparte: fusión pista + pista del mismo MKV, fusión pista + `.srt`
  coreano externo, y traducción de una pista.
- **Reserva de cupo**: lo que diga la cabecera de la pista (cota superior) o, sin
  estadísticas, `ESTIMACION_SIN_ESTADISTICAS` = 40.000 caracteres.
- `trabajos.ejecutar`, si el origen o el coreano son pistas sin extraer:
  1. **Fase `EXTRAYENDO`** (columna nueva `translation_job.fase`, migración
     `e81d4b0c9a37`): extrae del vídeo, en una pasada, las pistas que use.
  2. **Revisa lo elegido con el texto real**: una pista que resulta forzada (menos
     de 100 líneas), que no es ES/EN, o un coreano que no es coreano, hacen fallar el
     trabajo con el motivo, sin gastar nada. Si resulta inglesa en vez de española,
     el bilingüe pasa a `EN-KO`.
  3. **Ajusta la reserva** a la cifra exacta. Si es más de lo reservado y el
     proveedor ya no llega, falla antes de enviar; al reintentar, la elección busca
     otro.
  4. **Fase `GENERANDO`**: lo de siempre, leyendo por `lectura.leer_bloques`.
- Las dependencias de las tareas de fondo (sesión, traductor, sondeador,
  extractor) pasan a `api/dependencias.py`: el router de generación necesitaba el
  extractor, y tenerlas en cada router obligaba a importarse entre ellos.

### Verificación

- `uv run pytest` → **297 passed**. `ruff` limpio. Migración: `upgrade`, `alembic
  check`, `downgrade -1` y `upgrade` sobre la copia de la BD.
- **Contra la biblioteca real** (backend sobre la copia de la BD, `POST /translate`):

| Obra | Modo | Tiempo | Resultado |
|---|---|---|---|
| *Moonrise* 01 | Fusión pista 7 + pista 25 | **3 s** (ya extraída en el hito 2) | Calidad 1,0; 0 caracteres gastados |
| *Shingeki no Kyojin* 01 | Traducción con Azure | **60 s** extrayendo + **6 s** traduciendo | 279 líneas, 6.921 caracteres (reservados 40.000 por estimación y corregidos al extraer) |

Los dos bilingües quedan junto a sus vídeos en el NAS, con el nombre del vídeo:
`…Moonrise - 01 […].ES-KO.bilingue.srt` y `…Shingeki No Kyojin - 01.ES-KO.bilingue.srt`.
Los carteles de *Shingeki* no se traducen ni se cuelan.

**Aviso**: los 6.921 caracteres de Azure quedaron registrados en la **copia** de la
base de datos, no en la de desarrollo. El registro de Azure de la app (que no puede
consultar el consumo real) no los verá; son el 0,35 % del cupo mensual.

Commit `5bcfa94`.

## Hito 4 — Interfaz (2026-09-28)

### Qué se hizo

- **Backend**: el árbol da, por obra, `origen_en_video` y `caracteres_exactos`, y
  su `num_caracteres` sale de la misma función con la que el trabajo reserva cupo
  (`trabajos.caracteres_previstos`). Así la previsión de proveedor del frontend
  (`utils/cupos.repartir`) cuadra con la del backend también para las pistas sin
  estadísticas, que el árbol enseñaba como 0 caracteres.
- **Detalle de una obra**:
  - origen y coreano con la etiqueta «dentro del vídeo»;
  - líneas con su precisión: exactas, «≈» si salen de la cabecera, «por saber» si
    no hay estadísticas;
  - coste con «≈» mientras la pista no está extraída;
  - bloque «Pistas dentro del vídeo · sin extraer», con el botón **Extraer pistas**,
    una barra indeterminada mientras dura (pregunta cada 3 s) y el error, si lo hay.
- **Trabajos, cabecera y detalle**: la fase `EXTRAYENDO` («Extrayendo las pistas del
  vídeo: se lee el fichero entero») con una barra indeterminada, sin porcentaje. Los
  títulos de los trabajos desde pistas salen del nombre del vídeo (`Moonrise - 03`,
  no la carpeta de la serie).
- **Escaneo**: tras escanear, `useSondeo` sigue la lectura de pistas. La cabecera
  muestra «Leyendo pistas · N de M», la tarjeta del escaneo su barra, y el árbol se
  recarga cada 15 s mientras dura y al acabar. Si `ffprobe` falla, se dice.
- Obras sin subtítulos: «sin subtítulos» en vez de «subs en MKV», y el aviso del
  detalle ya no habla de una Fase 5 futura.
- Selección múltiple: total con «≈» y la nota de por qué.

### Verificación

- `npm run build` y `oxlint` limpios; backend **298 passed**.
- **En el navegador** (Chrome con `playwright-core`, backend sobre la copia de la BD,
  sin errores en consola):
  - *Jujutsu Kaisen* 01: «Pista 9 · ≈ 390 líneas», «Se traducirá con Azure · ≈
    27.177 caracteres» y el bloque de extracción.
  - *Moonrise* 02: **Extraer pistas** → barra indeterminada → a los **69 s** la
    muestra y «Fusión · casan bien, calidad 0,99».
  - Tres episodios de *Shingeki*: «≈ 120.000 caracteres» (3 × la estimación de
    40.000: sus pistas no traen estadísticas) con la nota.
  - *Moonrise* 03, **Generar bilingüe**: en Trabajos, «Extrayendo las pistas del
    vídeo» con la barra indeterminada y la píldora «Moonrise - 03 · extrayendo
    pistas»; termina como fusión con calidad 1,00, 0 caracteres. Su bilingüe queda
    en el NAS junto al vídeo.
  - Carpetas → **Escanear**: «Leyendo las pistas de subtítulo…» y, sin vídeos nuevos,
    termina en segundos.
