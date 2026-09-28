# Bitácora — Fase 3: traducción + generación bilingüe

Plan: `docs/plans/plan-fase3.md`. Esta bitácora recoge lo que acabó pasando, hito a
hito, con las decisiones tomadas por el camino y cómo se verificó.

## Decisiones previas (2026-09-28)

Antes de escribir código se fijó con el usuario la regla de negocio que simplifica
toda la fase: solo bilingües `ES-KO` o `EN-KO`; sin origen ES/EN la obra no es
elegible; si ya hay un coreano se fusiona en vez de traducir; la publicidad de YTS
no se filtra. Además, el usuario pidió dos cosas nuevas: la vía rápida 1:1 en la
alineación cuando coinciden los bloques y el renombrado a nomenclatura Plex. Todo
quedó reflejado en el plan.

## Hito 1 — Detección de idioma ampliada (2026-09-28)

### Qué se hizo

- `srt_parser.analizar_nombre`: el nombre se parte también por `_`, `-`, espacios,
  corchetes y paréntesis, y devuelve idioma **y** flags (`es_forzado`, `es_sdh`). Solo
  se leen los tokens del **sufijo**, de derecha a izquierda, mientras sean flags o
  idioma: así `Hi.Mom.2021.srt` no se toma por SDH.
- `srt_parser.detectar_idioma_desde_contenido`: `KO` por proporción de hangul, `ES`/`EN`
  por densidad de palabras frecuentes propias de cada idioma, `UNKNOWN` si nada
  destaca o hay menos de 50 palabras.
- `srt_parser.detectar_idioma`: combina las dos; manda el contenido cuando decide.
- Lectura en CP949 antes del respaldo latin-1.
- `subtitle_file`: columnas `es_forzado`, `es_sdh` y `version_analisis`, con la
  migración `6f170d42eb87`. `scanner.VERSION_ANALISIS = 2` hace que el próximo escaneo
  reprocese lo ya inventariado.

### Calibración contra la biblioteca real

Antes de fijar umbrales se pasó el detector a los 686 `.srt` de `Z:\Pelis` y se
comparó con lo que declara el nombre:

| Nombre dice | Contenido dice | Ficheros |
|---|---|---|
| ES | ES | 123 |
| EN | EN | 120 |
| KO | KO | 11 |
| FR / DE / IT / PT / JA / ZH | UNKNOWN | 112 |
| ES | EN | **1** |
| ES / EN | UNKNOWN | 6 (forzados cortos y un SDH) |
| KO | UNKNOWN | **1** |

**Cero falsos positivos**: ningún fichero en otro idioma pasa por español o inglés.
Densidad de palabras frecuentes medida:

| Grupo | Densidad |
|---|---|
| ES completo más pobre (un SDH lleno de acotaciones) | 0,11 |
| EN completo más pobre | 0,19 |
| Otro idioma, máximo en ES (francés, portugués) | 0,056 |
| Otro idioma, máximo en EN (polaco: `i`, `to`, `on` son palabras polacas) | 0,068 |

El umbral se fijó en **0,10**, entre las dos poblaciones. El 0,15 inicial dejaba fuera
el SDH español de *Skull*.

Las tres anomalías resultaron ser hallazgos:

1. **`It Ends\Subs\spa.srt` es inglés** (2588 palabras frecuentes EN contra 8 ES). El
   nombre miente. Por eso el contenido manda también cuando el nombre sí declara
   idioma, no solo cuando no dice nada, como preveía el plan.
2. **`Backrooms….ko.srt` está en CP949**, no en UTF-8. Leído como latin-1 salía una
   ensalada sin hangul. Se añadió CP949 como segunda opción, aceptada solo si el
   resultado es coreano.
3. **`Skull … Spanish [SDH].spa.srt`** quedaba por debajo del umbral inicial.

### Verificación

- 111 tests en verde (88 previos + 23 nuevos), `ruff` limpio.
- Migración aplicada, deshecha y reaplicada sobre la BD de desarrollo; `alembic check`
  sin diferencias.
- Escaneo real de `Z:\Pelis` con el scanner de la app sobre una BD temporal (53 s por
  la red, 686 ficheros, 0 errores):

| | Antes (solo nombre) | Ahora |
|---|---|---|
| Obras con origen ES/EN no forzado | 128 | **171 de 175** |
| Obras con coreano | — | 12 (11 también con ES/EN) |

Las 4 sin origen lo están con razón: dos obras solo traen danés (`RETAIL DKSUBS`),
*The Sixth Sense* solo trae coreano y *The Naked Gun* solo el anuncio de YTS.
*The Wailing* ya no cuenta como coreana: el `KOREAN` del nombre era el de la película
y su `.srt` es inglés.

Todavía no se descartan los forzados encubiertos (por número de bloques): eso es el
hito 2.

## Hito 2 — Selección del origen y estado `SIN_ORIGEN` (2026-09-28)

### Qué se hizo

- **`services/obras.py`** (nuevo): agrupa vídeos y subtítulos en obras, y lo usan el
  árbol y la selección. Reglas: la subcarpeta `Subs\` es transparente; un subtítulo
  va con el vídeo de su misma base; si no casa pero la carpeta tiene **un solo
  vídeo**, es de ese vídeo (carpeta de película); si no, forma obra por su base.
- **`naming.base_sin_idioma`** quita ahora también los flags (`Pelicula.en.forced.srt`
  → `Pelicula`), con el mismo criterio de sufijo que `analizar_nombre`.
- **`services/subtitles/seleccion.py`** (nuevo): propone origen ES/EN y coreano, y
  devuelve cada candidato con su motivo de descarte (`ERROR`, `IDIOMA`, `FORZADO`,
  `POCOS_BLOQUES`). Admite un override manual (`origen_preferido_id`), que la API
  expondrá en el hito 8.
- **Árbol**: estado `SIN_ORIGEN`, contador `num_sin_origen` y, por hoja,
  `subtitulo_origen_id` y `subtitulo_coreano_id`. `num_caracteres` pasa a ser el
  del origen (lo que costaría traducir), no la suma de todos los subtítulos.
- **Frontend (mínimo)**: `types.ts` al día, insignia `⚠ sin subs ES/EN` y marca
  `🇰🇷 fusionable`. La selección manual y el resto de la interfaz van en el hito 9.

### Decisiones tomadas por el camino

1. **La referencia para detectar forzados encubiertos excluye los SDH.** En
   *Predator: Killer of Killers* el SDH tiene 994 bloques, y el resto de idiomas unos
   430: con el SDH como referencia, el inglés completo (367) se descartaba por
   forzado.
2. **Mínimo absoluto de 100 bloques.** La regla relativa (40 % del mayor) no ve un
   forzado encubierto que es el único subtítulo de su obra: *Thunderbolts* (33
   bloques) y *Frankenstein* (90) salían como origen. La película real con menos
   diálogo, *Eraserhead*, tiene 144. El override manual se salta este mínimo y la
   regla relativa, porque el usuario puede saber que un subtítulo corto es completo.
3. **Un subtítulo ilegible ya no marca la obra entera como `ERROR`** si hay otro
   origen válido. `ERROR` queda para las obras sin origen y con algún fichero roto.
4. **El filtro del árbol por estado** conserva las obras enteras (con todos sus
   subtítulos) si alguno cumple el filtro, porque la selección necesita verlos todos.
5. En el orden de preferencia, **el idioma pesa más que el SDH**: un español SDH gana
   a un inglés normal. El usuario prefiere el español.

### Verificación

- 134 tests en verde (111 previos + 23 nuevos: `test_seleccion.py` con los casos
  reales, `test_obras.py`, y casos nuevos en el árbol y en `naming`). `ruff` limpio.
  `npm run build` sin errores de tipos.
- Sobre la carpeta `Pelis` real (BD temporal del hito 1):

| | Resultado |
|---|---|
| Obras (hojas) | 228, ninguna rama `Subs` suelta |
| `PENDIENTE` (con origen) | **173**, de ellas **11 fusionables** (con coreano) |
| `SIN_ORIGEN` | 6 |
| `SIN_SUBTITULOS` (solo vídeo) | 49 |
| Origen elegido | 121 en español, 52 en inglés |

Las 6 sin origen, una a una: dos solo con danés, *The Sixth Sense* solo con coreano,
*The Naked Gun* solo con el anuncio de YTS, y *Frankenstein* y *Thunderbolts* con un
único subtítulo forzado encubierto. Los casos del plan eligen lo esperado: *Mercy* →
`Latin American.spa.srt` (2015 bloques), *Jojo Rabbit* → `Jojo Rabbit.srt`, *Bugonia*
→ el `.spa.srt`, *Jaws* → español + coreano.

**Caso límite conocido**: *Perfect Days* tiene dos copias del vídeo en la misma
carpeta, así que no se sabe de cuál son sus `Subs\`. Se muestran como obras aparte en
vez de adivinar. *A Quiet Place Part II* entra como origen con 343 bloques: el plan
lo sospechaba forzado, pero es una película de muy poco diálogo y queda por encima
del mínimo; si resultara incompleto, el override lo resuelve.
