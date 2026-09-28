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

## Hito 3 — Renombrado a la nomenclatura de Plex (2026-09-28)

### Qué se hizo

- **`services/subtitles/renombrado.py`** (nuevo), en dos pasos:
  - `proponer(db)` calcula la lista `actual → nuevo` sin tocar el disco.
  - `aplicar(db, ids)` renombra solo los confirmados. Recalcula la propuesta en ese
    momento, **nunca sobrescribe**, trata un fallo del disco como rechazo y hace
    commit fichero a fichero, para que la base de datos no se quede apuntando a un
    nombre que no existe si la red se corta a mitad.
- Qué se propone: subtítulos **junto al vídeo** en obras de **un solo vídeo**, cuyo
  nombre no declara el idioma que dice el contenido (porque no dice ninguno o porque
  miente). El nombre nuevo es `<vídeo>.<spa|eng|kor>[.forced][.sdh].srt`
  (`CODIGOS_PLEX` en `enums.py`). Un nombre que ya declara bien el idioma se respeta
  aunque no siga la nomenclatura al pie de la letra (`.en` no se cambia a `.eng`).
- Conflictos: `EXISTE` (ya hay un fichero con ese nombre), `DUPLICADO` (dos
  subtítulos de la obra quieren el mismo; se lo queda el más completo) y
  `ERROR_DISCO`.
- La API y la pantalla llegan en los hitos 8 y 9; de momento es un servicio.

### Decisión tomada por el camino

**Los forzados encubiertos se renombran como forzados.** La primera propuesta real
convertía el `.srt` de 15 bloques de *The Gorge* en `….eng.srt`, y Plex lo habría
ofrecido como el subtítulo inglés completo. Ahora, si la selección lo descarta por
`POCOS_BLOQUES`, el nombre nuevo lleva `.forced`.

### Verificación

- 147 tests en verde (13 nuevos en `test_renombrado.py`, entre ellos el de no
  sobrescribir un destino aparecido entre la propuesta y la confirmación). `ruff`
  limpio.
- **Propuesta real sobre la carpeta `Pelis`, sin aplicar**: 106 renombrados.

| | Ficheros |
|---|---|
| A `.eng.srt` | 84 |
| A `.spa.srt` | 16 |
| A `.eng.forced.srt` (forzados encubiertos) | 6 |
| Con conflicto `EXISTE` | 2 |

Los dos conflictos (*Jaws*, *The End Of Oak Street*) son un inglés sin sufijo que
duplica otro que ya se llama `.eng.srt`; se quedan como están. **No se ha renombrado
nada en la biblioteca**: el usuario prefiere aplicarlo él desde la pantalla (hito 9).

## Hito 4 — Alineación del coreano existente (modo fusión) (2026-09-28)

### Qué se hizo

**`services/subtitles/alineacion.py`** (nuevo): `alinear(origen, coreano)` devuelve un
texto coreano por bloque de origen, más el desplazamiento y el factor de velocidad
aplicados, el método, la calidad y cuántos bloques coreanos no encontraron sitio.

1. **Desfase global**: búsqueda gruesa (±60 s en pasos de 0,5 s) y fina (pasos de
   50 ms) del desplazamiento, para cada factor de velocidad (1, 25/23,976 y su
   inverso), maximizando el tiempo en pantalla compartido. El solape total se
   calcula recorriendo las dos listas a la vez, en tiempo lineal: se evalúa unas 700
   veces por película.
2. **Vía rápida 1:1** (la idea del usuario): mismo número de bloques y cada par
   solapado tras corregir el desfase. Contar no basta por sí solo, y por eso se
   comprueba el solape par a par.
3. **Vía general**: cada bloque coreano va con el de origen con el que más comparte;
   varios en el mismo bloque se unen en orden; uno sin solape se acepta en el
   vecino si está a menos de 0,5 s.
4. **Calidad**: fracción de bloques coreanos que comparten con su bloque de origen al
   menos la mitad de su duración. Umbral **0,7**.

### Calibración contra la biblioteca real

Las 11 obras con origen ES/EN y coreano, en menos de 1 s cada una:

| Obra | Origen / KO | Desfase | Calidad |
|---|---|---|---|
| Backrooms | 857 / 1055 | −0,05 s | 0,82 |
| Good Luck Have Fun Don't Die | 1711 / 2218 | 0 | 0,94 |
| Jaws | 1253 / 1273 | +0,45 s | 0,90 |
| Obsession | 1958 / 1720 | **+9,50 s** | 1,00 |
| Predator: Killer of Killers | 424 / 436 | 0 | 0,99 |
| Project Hail Mary | 1675 / 1694 | 0 | 0,99 |
| Ricky Gervais: Mortality | 1160 / 1164 | 0 | 1,00 |
| Se7en | 1513 / 1573 | −1,20 s | 0,75 |
| The End Of Oak Street | 1133 / 1343 | 0 | 0,87 |
| The Gorge | 753 / 767 | 0 | 0,99 |
| Wolfs | 1092 / 1121 | 0 | 0,98 |

**Control negativo** (el coreano de cada película contra el origen de otra): entre
0,12 y **0,58**. En películas con mucho diálogo el azar ya solapa bastante, así que el
umbral provisional de 0,6 quedaba pegado a los falsos positivos. Se subió a **0,7**.

Ninguna pareja real tiene el mismo número de bloques, así que en la práctica todas
van por la vía general. La vía 1:1 queda cubierta por los tests.

*Se7en* (0,75) se revisó por si había deriva, es decir, un corte de montaje distinto
que cambiara el desfase a mitad de película. No la hay: el desfase es −1,2 s de
principio a fin. La calidad más baja se debe a que el coreano corta las frases más
finas y muchos bloques caen a caballo de dos. Muestra de *Jaws*: `Más despacio.`
recibe `천천히 가` ("ve despacio") y `Espera.` se queda vacío, porque el coreano no
traduce esa frase.

### Verificación

- 154 tests en verde (7 nuevos en `test_alineacion.py`: 1:1, desfase, velocidad,
  segmentación distinta, invariante de un texto por bloque, bloque descolocado y
  coreano de otra versión). `ruff` limpio.
- Ningún proveedor de traducción involucrado: cero caracteres de cuota.

## Hito 5 — Tabla `translation_job` (2026-09-28)

### Qué se hizo

- Modelo `TrabajoTraduccion` (`models/translation_job.py`) y enums `ModoTrabajo`
  (`TRADUCCION` / `FUSION`) y `EstadoTrabajo` (`QUEUED` / `RUNNING` / `DONE` /
  `FAILED`). Propiedad `activo`, para que el frontend sepa si seguir sondeando.
- Migración `b9edc39727eb`, generada con autogenerate, revisada (correcta tal cual:
  tabla, dos FKs `SET NULL` y dos índices) y reescrita con el estilo de las
  anteriores.
- `modelo-datos.md` y `.html` al día, en el mismo commit que la migración.

### Decisión tomada por el camino

**El trabajo es historial, no índice.** Es la primera tabla que no se puede
reconstruir escaneando: sus `num_caracteres` son la cuota consumida que agregará la
Fase 4. Por eso las FKs son `ON DELETE SET NULL` en vez de `CASCADE`, y el trabajo
guarda copia de sus rutas. Esas rutas copiadas preparan, además, el requisito del
usuario para la Fase 5 (fusionar desde pistas embebidas en MKV): el origen de un
trabajo no tendrá por qué ser una fila de `subtitle_file`. El principio rector de
`CLAUDE.md` recoge la excepción.

### Verificación

- 158 tests en verde (4 nuevos en `test_translation_job.py`, entre ellos que el
  trabajo sobrevive, con su ruta y sus caracteres, a que un escaneo borre su `.srt`).
- Migración aplicada, deshecha y reaplicada sobre la BD de desarrollo;
  `alembic check` sin diferencias.
