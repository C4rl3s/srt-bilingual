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

## Hito 6 — `Translator` multi-proveedor + DeepL (2026-09-28)

### Contexto: DeepL ya no tiene API gratuita permanente

Al ir a crear la cuenta, el usuario encontró que DeepL solo ofrece una prueba. Se
comprobó: desde julio de 2026 DeepL ya no da de alta cuentas nuevas en su API Free
(500 000 caracteres al mes) y la ha sustituido por planes con cupo total o de pago.
Con los datos reales, traducir la biblioteca entera son **~6 M de caracteres**: 162
películas, con una mediana de 34 000 caracteres cada una y un máximo de 98 000; las
otras 11 van por fusión. El usuario abrió una cuenta con **1 M de caracteres** "para
ir tirando" y pidió dejar la capa preparada para cambiar de proveedor cuando caduque.
Candidato natural para el relevo: Azure Translator, con 2 M de caracteres al mes
gratis en su plan F0.

### Qué se hizo

- `services/translation/base.py`: `Translator` como `Protocol` con `runtime_checkable`
  (nombre + `traducir(textos, origen, destino)`) y las excepciones comunes
  (`ErrorTraduccion`, `CuotaAgotada`, `ProveedorNoDisponible`). Nada fuera de este
  paquete importa el SDK de DeepL.
- `services/translation/deepl_provider.py`: `TraductorDeepL` sobre el SDK oficial
  (`deepl` 1.32). Lotes de 50 textos, textos vacíos sin enviar y recolocados en su
  sitio, `preserve_formatting` y comprobación de la invariante (tantos textos de
  vuelta como enviados). Traduce las excepciones del SDK a las comunes.
- `services/translation/registry.py`: del nombre al proveedor. Se elige con
  `TRANSLATION_PROVIDER` en el `.env`, y cada proveedor exige su propia clave solo
  si se usa.
- `config.py`: `translation_provider`. `backend/.env` creado a partir de la
  plantilla (lo ignora git) y la clave puesta por el usuario.
- `TraductorFalso` en `conftest.py`: ningún test llama a DeepL.

### Lo que se comprobó del SDK, en vez de suponerlo

Se inspeccionó el SDK instalado antes de escribir el proveedor. Ya **reintenta 5
veces** con espera creciente ante cortes de red y respuestas 429, así que no hay
reintentos propios, contra lo que decía el plan. Cada resultado trae
`billed_characters`. La documentación actual de la API **no limita el número de
textos** por petición, solo su tamaño (128 KiB): los lotes de 50 son una elección
prudente (~4 KB), no un límite de DeepL.

### Verificación

- 168 tests en verde (10 nuevos en `test_translation.py`: orden e idiomas, lotes,
  vacíos, invariante, cuota agotada, clave rechazada y registro). `ruff` limpio.
- **Prueba de humo real** con tres textos de *Jaws* (~60 caracteres):
  `- ¿Cómo era tu nombre?\n- Chrissie.` → `- 이름이 뭐였지?\n- 크리시.`, y
  `No estoy borracho. ¡Espera!` → `난 취하지 않았어. 잠깐만!`. Respeta los saltos de
  línea y los guiones de diálogo; el texto vacío vuelve vacío sin enviarse. El
  contador de uso de la cuenta (límite 1 000 000) aún marcaba 0 justo después:
  DeepL lo actualiza con retraso.

## Hito 7 — Generación del bilingüe (2026-09-28)

### Qué se hizo

- **`services/bilingual.py`** (nuevo), en tres piezas:
  - `componer(bloques_origen, textos_coreano)` pone el coreano debajo de cada bloque
    y conserva índice, inicio y fin. Un bloque sin coreano (en la fusión, una frase
    que el coreano no traduce) queda solo con el original, sin línea vacía. Verifica
    la invariante de un texto por bloque.
  - `escribir(bloques, ruta)` escribe en UTF-8 de forma **atómica**: primero a un
    temporal en la misma carpeta (`.nombre.xxxx.tmp`, que el escáner ignora) y luego
    un renombrado con `os.replace`. Si falla, borra el temporal y no toca un bilingüe
    anterior.
  - `generar` = `componer` + `escribir`.
- Recibe **bloques y no rutas** (el cambio del 2026-09-28): sirve igual para la
  traducción, para la fusión y, en la Fase 5, para pistas extraídas de un MKV.
- **`naming.ruta_bilingue_de_obra(directorio, nombre_obra, origen)`**: el bilingüe va
  junto al vídeo y con su nombre, aunque el origen viva en `Subs\`.
  `derivar_nombre_bilingue` pasa a apoyarse en ella.

### Detalle de la librería `srt` que había que saber

`srt.compose` **renumera por defecto** (`reindex=True`). Sin `reindex=False` el
bilingüe saldría numerado 1, 2, 3… aunque el original empezara en 5 o tuviera saltos.
Se comprobó antes de escribir el código, y hay un test que lo vigila.

### Verificación

- 177 tests en verde (9 nuevos en `test_bilingual.py`): índices y tiempos idénticos
  releyendo el fichero, numeración original sin renumerar, UTF-8, los dos modos
  (salida de un traductor y de la alineación) y la escritura atómica ante un fallo.
- **Bilingüe real de *Jaws* por fusión, sin gastar cuota**, escrito fuera de la
  biblioteca: 1253 bloques con índices y tiempos **idénticos** al original, y 1130
  (90 %) con su coreano debajo. Muestra:

```
6
00:02:40,626 --> 00:02:43,094
No estoy borracho. ¡Espera!
나 안 취했어!
좀 천천히 가!
```

### Prueba en Plex (2026-09-28)

El usuario probó el bilingüe de *Jaws* copiado junto al vídeo. **Plex lo muestra como
"Español (KO)"**, y el usuario da el nombre por bueno. La fusión se ve "bastante
correcta", pero se detectó un problema, solo del modo fusión:

**Bloques coreanos que abarcan varias frases de origen.** El coreano a veces junta en
un bloque lo que el español dice en dos (*Jaws*, 2:36: `Espera.` + `Más despacio.`
frente a un único `천천히 가 / 천천히 좀 가라고`). Como la alineación asigna cada bloque
coreano entero a **una sola** frase de origen, la de mayor solape, en pantalla sale
una frase española sola y, justo después, otra con dos frases coreanas de golpe.

Medido en las 11 películas: **355 de 14 364 bloques coreanos (2,5 %)**, concentrados
en las películas antiguas (*Se7en* 9,2 %, *Jaws* 7,6 %). En el **83 %** de esos casos
el bloque coreano trae tantas líneas como frases de origen abarca, así que se puede
**repartir por líneas en orden**. El 17 % restante (una sola línea coreana sobre dos
frases) solo se arreglaría fundiendo las frases de origen en un bloque, lo que
rompe la regla de que los tiempos del origen mandan: queda como idea para más
adelante.

#### Hecho: reparto por líneas (2026-09-28)

`alineacion._repartir_por_lineas`: un bloque coreano que **cubre al menos la mitad**
de cada una de dos o más frases de origen, y trae **exactamente tantas líneas** como
frases cubre, se reparte línea a línea en orden. Con otro número de líneas va entero
a su frase de mayor solape, como antes. La **calidad no cambia**: se sigue midiendo
sobre la asignación por solape, así que el umbral de 0,7 y su control negativo siguen
valiendo. `ResultadoAlineacion` informa de cuántos bloques se repartieron.

Sobre las 11 películas: **296 repartos**, exactamente los que predijo la medición, y
la calidad idéntica en todas. En *Jaws*, las frases españolas sin coreano bajan de
**123 a 44**. El bilingüe de *Jaws* se regeneró junto al vídeo para verlo en Plex:

```
4
00:02:36,255 --> 00:02:37,722
Espera.
천천히 가

5
00:02:38,624 --> 00:02:40,524
Más despacio.
천천히 좀 가라고
```

180 tests en verde (3 nuevos: reparto, líneas que no cuadran y diálogo bajo una sola
frase).

#### Idea del usuario para estudiar más adelante: agrupar por el lado que menos corta

Propuesta del usuario (2026-09-28): en vez de que el origen marque siempre los
tiempos, que mande **el lado que corta menos las frases**. En *Jaws*, el coreano dice
en un bloque largo lo que el español dice en dos cortos, así que se **agrupan las dos
frases españolas** en un único bloque bilingüe que dura lo que ambas juntas, con todo
el coreano debajo. No quedaría ni la frase aislada ni el coreano amontonado.

El propio usuario señala el límite: no sirve elegir un lado para toda la película,
porque en la misma película unas veces junta el coreano y otras el español (en
*Jaws*, `No estoy borracho. ¡Espera!` es un bloque en español y dos en coreano).

**Cómo generalizarlo** (planteado al confirmarla): decidir **tramo a tramo**. Los
bloques de los dos idiomas que se solapan de forma sustancial se encadenan en grupos
(componentes conexas del grafo de solapes), y cada grupo sale como un solo bloque
bilingüe: todo su origen arriba, todo su coreano abajo, desde el primer inicio hasta
el último fin. Donde los cortes coinciden (grupos 1+1) queda igual que hoy.

**A estudiar:**

- **Cadenas largas**: con diálogo rápido y cortes desfasados, A1–K1–A2–K2… podrían
  encadenarse en un bloque enorme. Hará falta un solape mínimo para encadenar y un
  tope de duración o de frases por grupo.
- **Excepción a "mandan los tiempos del origen"**, solo en el modo fusión: los bloques
  agrupados duran más y llevan más texto a la vez en pantalla.
- **Combinación con el reparto por líneas**: si el bloque coreano trae tantas líneas
  como frases abarca, repartir conserva los cortes finos y se lee mejor. Agrupar
  quedaría para el resto (el 17 % de una sola línea y los casos mezclados).
- **Cambio de contrato**: hoy la alineación devuelve un texto por bloque de origen y
  el generador conserva la lista de bloques. Agrupar obliga a que la alineación
  devuelva **bloques nuevos** (tiempos y textos de los dos lados), así que toca
  también a `bilingual.componer`.
- Medirlo con el mismo script que contó los 355 casos, antes y después, y verlo en
  Plex con *Jaws* y *Se7en*, las dos películas con más casos.

### Pendiente para el hito 8

El escáner detecta un bilingüe existente buscándolo **junto al subtítulo de origen**
(`derivar_nombre_bilingue`). Con la regla nueva, el bilingüe de un origen en `Subs\`
va junto al vídeo, así que el escáner no lo vería y la obra no pasaría a `DUAL`. Al
crear los trabajos en el hito 8 hay que llevar esa detección al nivel de obra, con
`ruta_bilingue_de_obra`.
