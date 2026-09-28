# Fase 5 — Subtítulos incrustados en MKV

## Contexto

Anime y Series son **todo MKV sin un solo `.srt` al lado**: los subtítulos viajan
dentro del contenedor. Hoy el árbol los dibuja, pero como `SIN_SUBTITULOS`, y no se
les puede generar nada. Esta fase los abre.

Lo que pide el usuario (2026-09-28), dos casos:

1. **Traducción desde una pista incrustada**: el MKV trae una pista ES/EN y no hay
   coreano → se traduce esa pista y sale el bilingüe.
2. **Fusión con una pista incrustada**: el MKV trae una pista ES/EN y hay coreano,
   ya sea **otra pista del mismo MKV** o un **`.srt` externo** → se fusionan con el
   modo fusión de la Fase 3, sin gastar cupo.

En los dos casos, el resultado es un **`.srt` bilingüe fuera del MKV**, junto al
vídeo y con su nombre, igual que hoy. **No se toca el MKV**: el plan original hablaba
de inyectar la pista bilingüe dentro del contenedor, y se descarta. Plex lee el
`.srt` externo, y reescribir ficheros de 1 GB por la red para añadir 30 KB es
lento y arriesga el original.

## Sondeo de la biblioteca real (2026-09-28)

Antes de diseñar, se midió lo que condiciona el diseño sobre ficheros reales.

**Coste de leer un MKV por la red** (el recurso compartido, `\\192.168.1.130`):

| Operación | Tiempo | Qué lee |
|---|---|---|
| `ffprobe` de las pistas | **0,8 s** por fichero | solo la cabecera |
| Extraer pistas con `ffmpeg` | **94 s** (842 MB) · **65 s** (590 MB) | el fichero **entero**, ~9 MB/s |

En un MKV los subtítulos van intercalados con el vídeo a lo largo de todo el
fichero: sacar una pista obliga a leerlo completo. Sacar tres cuesta lo mismo que
sacar una. En el NAS futuro, con el disco en local, esos 94 s serán unos pocos.

**Consecuencia: el escaneo solo puede sondear; extraer va dentro del trabajo.**

**Lo que dice la cabecera de cada pista:**

- Idioma (`spa`, `eng`, `kor`…) y título (`NF_Spanish`, `NF_Spanish(Latin_America)`).
- Marcas `default` y `forced`. **No son de fiar**: en *Shingeki* la pista española
  viene marcada `forced` y está completa (287 líneas).
- Estadísticas **cuando las escribió mkvmerge** (`NUMBER_OF_FRAMES`,
  `NUMBER_OF_BYTES`): en *Moonrise* sí, en *Shingeki* no.
  - `NUMBER_OF_FRAMES` = número de líneas, exacto (292 frente a 292 extraídas).
  - `NUMBER_OF_BYTES` ≈ **el doble** de los caracteres reales (15.099 frente a
    7.966): cada línea ASS arrastra ~25 bytes de campos. Sirve como cota superior
    para reservar cupo, no como cifra de consumo.

**Cómo es el texto:**

- *Moonrise* (Netflix): español y coreano con **exactamente los mismos tiempos**,
  línea a línea. La fusión saldrá perfecta.
- `ffmpeg` al convertir ASS → SRT mete etiquetas `<font face=… size=…><b>` en cada
  línea. **Se leerá el ASS directamente**, con un parser propio, en vez de
  convertirlo.
- *Shingeki* (fansub): de 287 líneas, 268 de estilo `Default` y el resto `Title`,
  `Sign_*`, `EndCard`: carteles. Pocos, pero mezclados con el diálogo si no se
  filtran.

**Biblioteca completa** (`ffprobe` a los 428 MKV de Anime, Series y Pelis; 475 s
en total, mediana de 0,32 s por fichero):

| | Anime | Series | Pelis |
|---|---|---|---|
| MKV | 215 | 184 | 29 |
| Pistas de subtítulo | 2388 | 2615 | 165 |
| Códecs de texto (`ass`, `subrip`) | 2388 | 1334 | 101 |
| Códecs de **imagen** (`hdmv_pgs_subtitle`, `dvd_subtitle`) | 0 | **1281** | 64 |
| Pistas con estadísticas | 95 % | 100 % | 24 % |
| Ficheros con origen ES/EN **en texto** | **207** | **49** | **22** |
| Ficheros con origen ES/EN **solo en imagen** | 0 | **130** | 5 |
| Ficheros con coreano en texto (**fusión sin cupo**) | **27** | **31** | **1** |

- **278 MKV tienen origen utilizable** y **59 se pueden fusionar sin gastar cupo**
  (*Moonrise*, *PLUTO*, *Silo*, *Pluribus*…).
- **Series trae 1281 pistas PGS**, que el sondeo del 08-09 no vio porque solo miró
  Anime. En **130 capítulos** (casi todo *Better Call Saul*) el español y el inglés
  **solo existen como imagen**. Sin OCR no hay texto que traducir.
- Los títulos confirman el problema de variantes: `Latin American`,
  `Spanish[LAT]`, `NF_Spanish(Latin_America)`, `European`, `Spanish[ESP]`,
  `español castellano`… Y los forzados y SDH se anuncian en el título: `Forced`,
  `(Forced)`, `FORZADOS`, `SDH`, `[CC]`, `[Signs]`.
- Hay 122 pistas marcadas `forced` en Anime, algunas de ellas completas (el caso de
  *Shingeki*).

## Alcance

**Dentro:**

1. Sondeo de las pistas de subtítulo de cada vídeo en el escaneo (`ffprobe`).
2. Las pistas de texto ES/EN/KO como **candidatos de su obra**, junto a los `.srt`
   externos, con la misma selección de origen y coreano de la Fase 3.
3. Extracción (`ffmpeg`) de las pistas dentro del trabajo, con caché.
4. Parser ASS (el 73 % de las pistas).
5. Traducción y fusión desde pistas, incluida la mezcla pista + `.srt` externo.
6. Interfaz: las pistas en el panel de detalle, el coste estimado y el paso de
   extracción en el progreso.

**Fuera:**

- Inyectar el bilingüe dentro del MKV (ver Contexto).
- **OCR de pistas de imagen** (PGS/VobSub). Dejaría fuera 130 capítulos de Series
  (ver sondeo). Se registran como candidatos descartados con motivo `IMAGEN`, para
  que la interfaz diga por qué esa obra no es elegible. Decisión del usuario
  (2026-09-28): el OCR queda como posible fase aparte.
- Pistas dentro de MP4/AVI: el sondeo solo midió MKV. `ffprobe` y `ffmpeg` las
  leen igual, así que el código no distingue el contenedor; si aparecen, entran.

## Diseño

### 1. Una pista es un subtítulo más

Una pista incrustada se guarda como **una fila de `subtitle_file`**, con referencia a
su vídeo. Alternativa descartada: tabla propia `subtitle_track`. Obligaría a
duplicar la selección de origen, los candidatos, los trabajos, las claves de
`translation_job` y el frontend, que hoy trabajan con `ArchivoSubtitulo`. Con una
fila más, todo eso funciona sin cambios, y la mezcla pista + `.srt` externo sale
gratis: son dos candidatos de la misma obra.

Columnas nuevas de `subtitle_file`:

| Columna | Tipo | Para qué |
|---|---|---|
| `video_id` | FK → `media_file` (`CASCADE`), nula | El MKV que la contiene. Nula en un `.srt` externo |
| `indice_pista` | entero, nulo | Índice del stream en el contenedor (`0:7`) |
| `titulo_pista` | texto, nulo | `NF_Spanish`, `Signs & Songs`… Se enseña y se usa para detectar forzados |
| `metricas_exactas` | booleano | `False` mientras bloques y caracteres salen de las estadísticas (o no se saben) |
| `ruta_extraida` | texto, nulo | La pista extraída, en la caché |

- `ruta` = `<ruta del mkv>#<índice>` (única y legible). `nombre` = `Pista 7 · NF_Spanish`.
- `formato` gana `ASS`, `PGS` y `VOBSUB` (el códec original se respeta al extraer).
- `media_file` gana `sondeado_mtime` (ver punto 2).
- La pista pertenece a la obra de su vídeo por `video_id`, no por el nombre
  (`obras.py`).
- Al borrarse el vídeo, sus pistas se van en cascada. El escaneo no las trata como
  ficheros huérfanos.

### 2. Sondeo en el escaneo

Nuevo `services/mkv/sondeo.py`. Para cada vídeo **nuevo o cambiado** (mismo criterio
de `mtime` y tamaño que hoy), `ffprobe` y reconciliación de sus pistas:

- Solo códecs de texto: `subrip`, `ass`, `ssa`, `webvtt`, `mov_text`.
- Idioma: la etiqueta ISO 639-2 con el mapa de `SUFIJOS_IDIOMA` que ya existe.
  Sin etiqueta (`und`), `UNKNOWN` hasta extraerla y mirar el contenido.
- Forzado y SDH: **por el título** (`Forced`, `Signs`, `SDH`, `CC`…) y la marca
  `hearing_impaired`. **La marca `forced` se ignora** (ver sondeo). Los forzados
  sin aviso los sigue cazando la regla de pocos bloques de la Fase 3, en cuanto se
  conocen los bloques.
- Métricas: `NUMBER_OF_FRAMES` → `num_bloques`; `NUMBER_OF_BYTES` →
  `num_caracteres` como cota superior; `metricas_exactas = False`. Sin
  estadísticas, las dos a 0.
- **Cambio en el hito 1**: las líneas de la cabecera **no se comparan entre
  pistas**. En los ASS de fansub, los carteles y el karaoke se trocean en decenas
  de eventos: la pista inglesa de *Jujutsu Kaisen* 01 declara 1023 frente a las 390
  de la española, que está completa. Con la regla del 40 % de la Fase 3, 57 obras
  de Anime acababan con origen inglés. Hasta extraer, solo se aplica el mínimo
  absoluto (100 líneas); la proporción, con cifras exactas.

**Cuándo**: **en segundo plano, tras el escaneo**. La primera pasada son 428 vídeos
≈ **8 min** por la red, demasiado para una petición HTTP. `POST /scan` sigue siendo
el inventario rápido de hoy y deja en cola el sondeo de los vídeos nuevos o
cambiados. `media_file` gana `sondeado_mtime`: el `mtime` con que se sondeó, así
que un vídeo sin cambios no se vuelve a abrir. Mientras dura, la interfaz muestra
«Leyendo pistas: 120 de 428» y las obras se van completando.

Las pistas de imagen se guardan igual, con `formato` `PGS`/`VOBSUB`, para que la
obra sepa que las tiene y la interfaz lo explique (descarte `IMAGEN`).

### 3. Extracción y caché

Nuevo `services/mkv/extraccion.py`:

- Una sola pasada de `ffmpeg` extrae **todas las pistas ES/EN/KO del vídeo** con
  `-c:s copy` (sin convertir): la primera obra de un MKV paga la lectura y el
  resto de sus pistas quedan listas.
- Van a una **caché** (`CACHE_DIR`, por defecto `backend/cache/`), en
  `pistas/<video_id>/<índice>.<ass|srt>`. Es reconstruible como la BD; si el vídeo
  cambia (`mtime`), se invalida.
- Tras extraer, se parsea cada pista y se rellenan las **métricas exactas** e,
  igual que con un `.srt`, el idioma por contenido si la etiqueta no lo decía.
- Rutas de `ffmpeg`/`ffprobe` configurables (`FFMPEG_PATH`), por defecto el `PATH`.

### 4. Parser ASS

Nuevo `services/subtitles/ass_parser.py` → `list[Bloque]`, como el de SRT:

- Solo líneas `Dialogue:` de la sección `[Events]`, con el formato que declare su
  línea `Format:`.
- Texto: fuera las etiquetas `{\...}`, `\N` y `\n` → salto de línea, `\h` →
  espacio.
- Se descartan los **dibujos** (`\p1`) y los estilos de **cartel** (el nombre
  contiene `sign`, `cartel`, `typeset`, `endcard`…).
- **Ampliado en el hito 2**, calibrando con *Jujutsu Kaisen* y *Kaiju No. 8*:
  también las líneas posicionadas a mano (`\pos`, `\move`), el karaoke (`\k`), los
  estilos de opening/ending y letras, y la abreviatura `Cart_` del fansub español.
- Ordenado por inicio; dos líneas simultáneas quedan como dos bloques.

Un solo punto de lectura para los trabajos y los candidatos:
`leer_bloques(sub) -> list[Bloque]`, que despacha a `.srt` o a la pista extraída.

### 5. Selección

La lógica de la Fase 3 no cambia: origen ES antes que EN, sin SDH, el más completo;
override manual. Dos ajustes:

- **Coreano del mismo MKV primero**: si el origen es una pista, se prefiere el
  coreano incrustado en el mismo vídeo (mismos tiempos, como en *Moonrise*) antes
  que un `.srt` externo.
- **Castellano antes que latino**: entre dos pistas españolas, la que no se anuncia
  como latinoamericana (`Latin`, `LAT`, `Latinoamérica`, `es-419`). Decisión del
  usuario (2026-09-28); el override manual permite elegir la latina por obra.
- **Motivo de descarte nuevo, `IMAGEN`**: pista PGS/VobSub.

### 6. Trabajos

- **Crear**: igual que hoy. Una traducción reserva `num_caracteres` como hoy, que
  en una pista sin extraer es la cota superior de las estadísticas. Sin
  estadísticas (el 5 % de las pistas de texto), se reservan 40.000 caracteres, por
  encima de la mediana de una película (34.000); se corrige al extraer.
- **Ejecutar**: si el origen o el coreano son pistas sin extraer, **primero se
  extraen** (nueva fase del progreso: «Extrayendo pistas del MKV»). Luego se
  corrige `caracteres_previstos` con la cifra exacta; si el proveedor asignado ya no
  tiene cupo, falla con el motivo y **Reintentar** vuelve a elegir, como con
  `CuotaAgotada`.
- El resto (traducir, alinear, `bilingual.generar`) no cambia: trabaja con
  `list[Bloque]`.
- **Añadido en el hito 3**: tras extraer, se revisa lo elegido con el texto real.
  Si la pista resulta ser un forzado (menos de 100 líneas de diálogo), no es
  ES/EN, o el coreano no es coreano, el trabajo falla con el motivo antes de gastar
  nada. Si resulta inglesa en vez de española, el bilingüe pasa a llamarse `EN-KO`.
  La fase va en una columna nueva, `translation_job.fase`.
- `translation_job` ya guarda las rutas copiadas: `ruta_origen` será
  `<mkv>#<índice>`.

### 7. API

| Endpoint | Cambio |
|---|---|
| `POST /scan` | Además del inventario, deja en cola el sondeo de los vídeos nuevos o cambiados |
| `GET /scan/sondeo` | **Nuevo**: progreso del sondeo de pistas (hechos / total) |
| `GET /library/tree` | Sin cambios de esquema: las obras de MKV dejan de ser `SIN_SUBTITULOS` |
| `GET /subtitles/{id}/candidatos` | Cada candidato dice si es pista (índice, título) y si está extraída. Sin extraer, **no hay muestra ni calidad de fusión** (costaría leer el MKV entero) |
| `POST /videos/{id}/extraer` | **Nuevo**: extrae las pistas de un vídeo en segundo plano, para ver muestra y calidad antes de generar |

### 8. Frontend

- Candidatos: `Incrustada · pista 7 · NF_Spanish`, junto a los `.srt`.
- Coste: `≈ 15.000 caracteres` cuando la cifra no es exacta.
- Detalle de una obra con pistas sin extraer: «La muestra y la calidad de la fusión
  se verán al extraer las pistas (≈ 1 min)» y botón **Extraer pistas**.
- Trabajos: la fase «Extrayendo pistas» antes de la barra de bloques.

### 9. Dependencias

- `ffmpeg`/`ffprobe` como binarios externos (ya instalados aquí con winget). No hace
  falta `pymkv2` ni ninguna librería Python: son dos llamadas a `subprocess`.
- Docker: `apt-get install ffmpeg` en la imagen, anotado para el README de
  despliegue.

## Orden de trabajo

| Hito | Contenido | Verificable por |
|---|---|---|
| **1** | Columnas nuevas (migración), `sondeo.py` en segundo plano tras el escaneo, pistas como candidatos de su obra | Tests con salidas reales de `ffprobe` guardadas como fixtures; escaneo real de las tres carpetas |
| **2** | Parser ASS, `extraccion.py` con caché, `leer_bloques` | Tests con fragmentos ASS reales; extracción de un episodio real |
| **3** | Trabajos con pistas: fusión pista + pista, pista + `.srt`, y traducción | Tests con extractor falso; *Moonrise* 01 fusionado (0 cupo) y un episodio de *Shingeki* traducido, vistos en Plex |
| **4** | Frontend | Recorrido en el navegador |
| **5** | Documentación: bitácora, modelo de datos, READMEs | — |

## Riesgos

1. **Lentitud por la red**: ~1,5 min por episodio antes de traducir. Aceptable en
   segundo plano; se va con el NAS. Una temporada entera en cola son ~20 min solo
   de lectura.
2. **Carteles que se cuelan**: el filtro por estilo depende de cómo nombre sus
   estilos cada grupo. Se revisará con las series reales.
3. **Coste estimado inexacto** hasta extraer: por eso se corrige al extraer y un
   trabajo que ya no cabe falla antes de gastar nada.
4. **Pistas del mismo idioma sin distintivo** (dos `NF_English`): se elige la más
   completa, como con los `.srt`; queda el override manual.
