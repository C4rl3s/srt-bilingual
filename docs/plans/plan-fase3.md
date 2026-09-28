# Fase 3 — Traducción + generación bilingüe

## Contexto

El 2026-09-08 esta fase estaba **bloqueada por dos motivos**, ambos documentados en
`docs/bitacora-inventario-video-y-arreglos.md`:

1. El recurso compartido estaba montado en **solo lectura**, así que la convención de
   dejar el `.bilingue.srt` junto al original habría fallado.
2. La única carpeta accesible era `Z:\Anime`: **215 `.mkv` y cero `.srt`**. Sin la
   Fase 5 (extracción de pistas embebidas) no había nada que traducir, y por eso se
   propuso adelantar la Fase 5 a esta.

**El 2026-09-27 los dos motivos han desaparecido.** Se concedió acceso a las tres
carpetas compartidas y se comprobó lo siguiente:

| Comprobación | Resultado |
|---|---|
| `Z:\Anime`, `Z:\Pelis`, `Z:\Series` se listan y recorren | Sí, las tres |
| Escritura (crear y borrar un fichero de prueba en cada una) | **OK en las tres** |

Inventario real del recurso:

| Carpeta | `.mkv` | `.mp4` / `.avi` | `.srt` |
|---|---|---|---|
| Anime | 215 | 0 | 0 |
| Series | 184 | 0 | 0 |
| **Pelis** | 29 | 196 | **686** |

Con 686 `.srt` externos repartidos en **176 carpetas de película**, la Fase 3 vuelve
a tener banco de pruebas propio y **deja de depender de la Fase 5**. Se retoma por
tanto el orden original del plan: primero traducción, después MKV.

---

## Regla de negocio: qué se genera y a partir de qué

Fijada con el usuario el 2026-09-28. Simplifica el resto del plan:

- **Destino único: coreano (`KO`).** Los bilingües son `ES-KO` o `EN-KO`, nada más.
- **Origen: español o inglés**, en ese orden de preferencia. Fijo, no configurable.
- **Sin origen ES/EN no hay bilingüe.** Si una obra no tiene ningún subtítulo válido
  en español o inglés es porque aún no se le ha buscado uno; la obra queda **no
  elegible** y el árbol lo dice (`SIN_ORIGEN`), en vez de intentar nada con otros
  idiomas.
- **Si ya hay un subtítulo coreano, no se traduce: se fusiona.** Se alinea el coreano
  existente con el origen ES/EN y no se gasta cuota de DeepL. Solo si la alineación
  sale mala se ofrece traducir, y lo decide el usuario.
- **La publicidad (`YTS`, `YIFY`…) no se filtra.** Al usuario no le molesta verla, y
  son uno o dos bloques por película (≈80 caracteres frente a ≈60 000): el ahorro de
  cuota no justifica el código.

---

## Lo que el sondeo de la biblioteca real obliga a añadir al plan

El plan original de esta fase daba por hecho que cada obra tenía *un* subtítulo de
origen evidente. Pasar el código actual sobre los 686 ficheros reales demuestra que
no es así, y ahí está el trabajo de verdad de la fase.

### Hallazgo 1 — El detector de idioma por nombre aguanta, pero se queda corto

`detectar_idioma_desde_nombre` sobre los 686 ficheros:

| Idioma | Ficheros |
|---|---|
| UNKNOWN | 325 |
| ES | 126 |
| EN | 113 |
| FR / PT / DE / KO / IT / ZH / JA | 122 |

**122 de las 176 obras** tienen ya un origen ES o EN detectado por nombre, y la
mayoría de los `UNKNOWN` son correctos: `fin`, `swe`, `dan`, `pol`, `dut`, `tur`…
idiomas que no soportamos y que no queremos como origen. El detector acierta con
`...spa.srt`, con `Subs/Latin American.spa.srt` y con `Subs/SDH.eng.HI.srt` (el token
`hi` ya está en `TOKENS_FLAG`, así que no lo confunde con hindi).

Se queda corto en dos patrones concretos:

- **RARBG**: `2_English.srt`, `5_Spanish.srt`. El detector parte el nombre solo por
  `.`, así que el token queda `2_english` y no casa. Afecta a 5 obras.
- **Flags entre paréntesis**: `Latin American (Forced).spa.srt` detecta ES
  correctamente pero **no se entera de que es forzado**, porque busca `forced` como
  token separado por puntos y aquí va dentro del paréntesis.

### Hallazgo 2 — 52 obras no declaran idioma en ningún nombre, y son mayoría inglés

Son el patrón YTS de un único `.srt` sin sufijo. **No vale asumir que ese fichero es
el inglés completo.** Contando palabras vacías (*stopwords*) sobre el contenido real:

| Veredicto por contenido | Obras |
|---|---|
| EN | 34 |
| ES | 15 |
| INCIERTO | 3 |

Los márgenes son enormes y nada ambiguos (*Megalopolis*: 3106 marcas ES contra 13 EN;
*Psycho*: 2166 EN contra 131 ES), así que **no hace falta ninguna librería de
detección de idioma**: un contador de stopwords sobre el texto ya parseado resuelve
el caso con código propio y legible. Los 3 inciertos son correctos como tales: dos
copias danesas (`RETAIL DKSUBS`) y un fichero de 4 bloques que solo tiene publicidad.

Recuperar estas 52 obras sube la cobertura de **122 a ~170 de 176**. Sin esto, 49
obras que **sí tienen** su subtítulo ES/EN en la carpeta se darían por no elegibles.

### Hallazgo 3 — El número de bloques delata los subtítulos forzados

Los `forced` (solo carteles y rótulos, inservibles como origen) se detectan mejor por
su tamaño relativo que por su nombre:

```
Mercy (2026)
   2015 bloques  Subs/Latin American.spa.srt           <- el bueno
   2009 bloques  Mercy.2026...spa.srt
   1779 bloques  Subs/European.spa.srt
     61 bloques  Subs/Latin American (Forced).spa.srt  <- forzado, lo dice el nombre
     42 bloques  Subs/European (Forced).spa.srt
```

Y hay forzados que **no lo dicen en el nombre**: `Frankenstein...srt` tiene 90
bloques, `A Quiet Place Part II...srt` tiene 343, y el `.srt` de *Jojo Rabbit* tiene
4 (solo el anuncio de YTS). La regla robusta es **comparar contra el mayor candidato
de la misma obra** y descartar lo que quede muy por debajo.

### Hallazgo 4 — 548 de 686 ficheros empiezan con publicidad

Ocho de cada diez `.srt` traen un bloque tipo `Downloaded from YTS.MX | Official YIFY
movies site` entre sus primeros bloques. **Decisión (2026-09-28): no se filtra** (ver
la regla de negocio). Se traduce y se cuenta como cualquier otro bloque.

### Hallazgo 5 — Dónde viven los `.srt` y cómo se agrupan

461 de los 686 están en una subcarpeta `Subs\` con nombres que **no contienen el
nombre de la obra** (`English.srt`, `Latin American.spa.srt`). Consecuencias:

- `base_sin_idioma` agrupa por nombre de fichero, así que esos subtítulos **no se
  agrupan con el vídeo de su película**: cuelgan del árbol como obras aparte bajo una
  rama `Subs`, con nombres de hoja tipo `English` o `Latin American`.
- Por obra: 113 tienen sus `.srt` solo junto al vídeo, 5 solo en `Subs\`, y **58 son
  mixtas** (el mismo subtítulo, duplicado en los dos sitios).

La agrupación se arregla tratando `Subs` como carpeta transparente: un `.srt` dentro
de `Subs\` pertenece a la obra del directorio padre. El bilingüe generado, en cambio,
se escribe **siempre junto al vídeo** y con el nombre base del vídeo, que es donde
Plex lo busca.

### Hallazgo 6 — 13 obras ya tienen subtítulo coreano

Sondeo del 2026-09-28 sobre `Z:\Pelis`: **13 `.srt` coreanos** por nombre (`.ko.srt`,
`kor.srt`, `Korean.kor.srt`), y **unas 10 de esas obras tienen también ES/EN**. Son el
banco de pruebas del modo fusión, y se prueba sin gastar cuota.

Muestra real, *Jaws* (1975), español frente a coreano:

```
ES  02:28,014 → 02:30,107     KO  02:27,681 → 02:30,284
ES  02:31,484 → 02:33,543     KO  02:31,185 → 02:33,454
ES  02:36,255 → 02:37,722     KO  02:36,257 → 02:39,460   <- KO junta en uno
ES  02:38,624 → 02:40,524                                    lo que ES parte en dos
```

Se ven los dos problemas que hay que resolver: un **desfase pequeño** (décimas de
segundo) y una **segmentación distinta** (cada fichero corta las frases por sitios
distintos).

Una trampa: *The Wailing* lleva `KOREAN` en el nombre porque **la película** es
coreana, no el subtítulo. El detector por contenido tiene que reconocer el hangul
para no fiarse del nombre en ese caso.

---

## Alcance de la fase

**Dentro:**

1. Detección de idioma ampliada (nombre y contenido; ES, EN y KO).
2. Selección del subtítulo de origen ES/EN: heurística automática + override manual
   desde la interfaz (decidido con el usuario el 2026-09-27). Estado `SIN_ORIGEN`
   para las obras no elegibles.
3. Renombrado a la nomenclatura de Plex de los subtítulos cuyo idioma se dedujo por
   contenido, con vista previa y confirmación (pedido el 2026-09-28).
4. **Modo fusión**: alinear un coreano existente con el origen, sin proveedor.
5. Interfaz `Translator` multi-proveedor + implementación DeepL con envío por lotes.
6. Generación del `.srt` bilingüe reutilizando las marcas de tiempo del original,
   común a los dos modos.
7. Trabajos asíncronos con `BackgroundTasks`, con progreso consultable.
8. Registro de caracteres consumidos por trabajo.

**Fuera** (no se toca en esta fase):

- Extracción de pistas embebidas en MKV (Fase 5). La fusión de esta fase le servirá
  tal cual a los 27 MKV de Anime con pista coreana. Requisito ya fijado para la
  Fase 5: fusionar pista ES/EN embebida con coreano embebido o externo y dejar el
  bilingüe fuera, como `.srt` (ver CLAUDE.md).
- Tabla `provider_usage` y panel de cuotas (Fase 4). Esta fase solo **registra** los
  caracteres de cada trabajo; agregarlos por mes y elegir proveedor según cuota libre
  es trabajo de la 4.
- Conversión ASS → SRT.
- Filtrado de publicidad (descartado, ver la regla de negocio).
- Idiomas de origen distintos de ES/EN y destinos distintos de KO.

---

## Diseño

### 1. Detección de idioma, ampliada

`app/services/subtitles/srt_parser.py` y `app/models/enums.py`:

- Partir el nombre también por `_` y `-`, no solo por `.`, para que caiga el patrón
  RARBG `2_English.srt`.
- Buscar los `TOKENS_FLAG` en el **nombre completo normalizado**, no solo como token
  entre puntos, para cazar `Latin American (Forced).spa.srt`.
- Nueva función `detectar_idioma_desde_contenido(bloques) -> Idioma`:
  - **KO** si una proporción clara de los caracteres del texto es hangul (rango
    Unicode `가`–`힣`). Es una comprobación directa, sin estadística.
  - **ES / EN** con el contador de stopwords validado arriba.
  - `UNKNOWN` cuando nada supera un umbral mínimo de densidad, en vez de inventarse un
    ganador.
- ~~El scanner la llama solo cuando el nombre no dice nada.~~ **Cambiado al
  implementar (hito 1):** manda el contenido siempre que da un veredicto claro, y el
  nombre solo cuando el contenido no decide (forzados de pocas líneas). Motivo: en
  la biblioteca real hay un `spa.srt` que es inglés de principio a fin. Los bloques ya
  están en memoria, así que no cuesta una lectura extra de disco.
- Añadido al implementar: lectura en **CP949** (con comprobación de hangul) antes del
  respaldo latin-1, porque el `.ko.srt` de *Backrooms* no es UTF-8.
- Añadido al implementar: columna `version_analisis` en `subtitle_file`. Sin ella, las
  filas ya inventariadas no se reprocesarían con las reglas nuevas hasta que su
  fichero cambiara en disco.

### 2. Selección del subtítulo de origen

Nuevo servicio `app/services/subtitles/seleccion.py`. Dada la lista de subtítulos de
una obra, puntúa cada candidato y propone el mejor:

| Criterio | Efecto |
|---|---|
| Idioma `ES` | Puntuación base alta |
| Idioma `EN` | Puntuación base menor (solo gana si no hay español válido) |
| Cualquier otro idioma o `UNKNOWN` | Descartado |
| Marcado `forced` por nombre | Descartado |
| `num_bloques` < 40 % del mayor candidato de la obra | Descartado (forzado encubierto) |
| `num_bloques` < 100 (añadido en el hito 2) | Descartado: forzado encubierto sin nada con qué compararlo |
| Marcado `SDH` / `CC` / `HI` | Penalizado, no descartado (sirve si no hay otro) |
| Mayor `num_bloques` | Desempate |

Ajustes del hito 2 (detalle en la bitácora): el "mayor candidato" se mide sin contar
SDH ni forzados, y el override manual se salta las dos reglas de tamaño. La
agrupación por obra (`Subs\` transparente, un solo vídeo por carpeta) vive en
`services/obras.py`, compartida con el árbol.

Devuelve el candidato elegido **y la lista completa con el motivo de cada descarte**,
para que la interfaz pueda enseñar por qué y permitir el override. Como elige **uno
solo** por obra, las 58 obras con subtítulos duplicados en `Subs\` no generan dos
bilingües.

Además localiza el **coreano** de la obra, si lo hay (mismas reglas de forzado), para
decidir el modo del trabajo.

Estados de obra en el árbol (`schemas/tree.py`, `EstadoObra`): se añade
`SIN_ORIGEN` (hay subtítulos, pero ninguno ES/EN válido). La hoja lleva además un
indicador de si hay coreano disponible, que es lo que distingue fusión de traducción.

### 3. Renombrado a la nomenclatura de Plex

Nuevo servicio `app/services/subtitles/renombrado.py`.

Plex asocia un subtítulo externo a su vídeo por el nombre:
`<nombre del vídeo>.<idioma>[.forced][.sdh].srt`. Un `Pelicula.srt` sin idioma, como
los 52 de YTS, aparece en Plex como idioma desconocido. Renombrarlo arregla la
biblioteca también para Plex, no solo para esta app.

- **Qué ficheros**: los que **están junto al vídeo** y cuyo idioma **no sale del
  nombre pero sí del contenido**. Se calcula al vuelo (el nombre no detecta idioma y
  `idioma_origen` no es `UNKNOWN`), así que no hace falta columna nueva.
- **Qué nombre**: base del vídeo de la obra + código de idioma + flags. Códigos
  ISO 639-2: `spa`, `eng`, `kor`, que Plex reconoce y que ya son mayoría en la
  biblioteca.
- **Fuera**: los de `Subs\` (moverlos cambiaría la organización de la carpeta) y las
  obras con cero o varios vídeos (no hay base de nombre inequívoca).
- **Nunca sobrescribe**: si el nombre de destino ya existe, no se renombra y se
  informa del conflicto.
- Añadido en el hito 3: también se proponen los que **mienten** en el nombre (el
  contenido dice otro idioma), y los forzados encubiertos que detecta la selección
  llevan `.forced`, para que Plex no los ofrezca como subtítulo completo.
- **Dos pasos, sin automatismos**: primero una **propuesta** (lista `actual →
  nuevo`), después el usuario confirma cuáles aplicar. Tocar los nombres de la
  biblioteca compartida no se hace a sus espaldas durante un escaneo.
- Al aplicar, se renombra en disco y se actualiza `ruta` en `subtitle_file`
  (`mtime` y tamaño no cambian, así que el siguiente escaneo no lo reparsea).

### 4. Modo fusión: alinear un coreano existente

Nuevo servicio `app/services/subtitles/alineacion.py`. Los tiempos del origen ES/EN
**mandan**, igual que en la traducción: el coreano se reparte sobre ellos.

```
alinear(origen: list[Bloque], coreano: list[Bloque]) -> ResultadoAlineacion
```

`ResultadoAlineacion` lleva un texto coreano por bloque de origen (cadena vacía si no
le toca ninguno), el desfase y el factor de velocidad aplicados, el método usado y una
medida de calidad.

Pasos:

1. **Corregir el desfase global.** Se prueban desplazamientos del coreano (p. ej. de
   −10 s a +10 s en pasos de 100 ms) y se queda el que maximiza el tiempo total
   solapado con el origen. Se prueban también los factores de velocidad típicos entre
   versiones (`1`, `25/23,976` y su inverso).
2. **Vía rápida: mismo número de bloques.** Si origen y coreano tienen tantos bloques
   como el otro y, tras corregir el desfase, **cada par `i`-ésimo se solapa** (o sus
   inicios están muy cerca), el emparejamiento es 1:1: el texto del bloque coreano `i`
   va debajo del bloque de origen `i`. Contar bloques no basta por sí solo: dos
   ficheros pueden coincidir en número por casualidad con frases cortadas en sitios
   distintos, y por eso se comprueba el solape par a par.
3. **Vía general: número distinto o pares que no casan.** Cada bloque coreano se
   asigna al bloque de origen con el que **más se solapa**. Si un bloque de origen
   recibe varios, se unen en orden con salto de línea. Si un coreano se reparte entre
   dos de origen, va solo al de mayor solape, para no duplicar texto. En el ejemplo de
   *Jaws*, el coreano de 02:36 cae en el primer bloque ES y el segundo se queda sin
   coreano, lo cual es aceptable: la línea coreana sigue en pantalla mientras se lee
   el español.
4. **Medir la calidad**: porcentaje de bloques coreanos que encontraron un bloque de
   origen con buen solape. Por debajo de un umbral (constante con nombre, calibrada
   con las ~10 obras reales; **0,7** tras el hito 4, ver la bitácora) la obra **no se
   fusiona automáticamente**: probablemente
   el coreano es de otra versión o montaje. Se muestra en la interfaz, y el usuario
   decide si traducir con DeepL.

Código propio y no `alass`/`ffsubsync`: es corto, didáctico, y los datos reales están
"casi alineados", no desordenados. Si algún caso real se resiste, `alass` queda como
plan B.

### 5. Interfaz de traducción

`app/services/translation/`:

- `base.py` — `Translator` como `Protocol`, con `traducir(textos, origen, destino) ->
  list[str]` y una propiedad de nombre. Protocol y no clase base abstracta para no
  obligar a heredar a futuros proveedores.
- `deepl_provider.py` — implementación con el SDK oficial (`uv add deepl`). Envío por
  lotes: DeepL acepta varios textos por petición, lo que reduce mucho las llamadas
  para los ~1500 bloques de una película. Reintentos con espera ante error de red o
  429: **ya los hace el SDK** (5 reintentos), comprobado en el hito 6.
- `registry.py` — devuelve el proveedor configurado por nombre. En esta fase solo
  DeepL; la Fase 4 le añadirá la selección por cuota.

**Cambio del 2026-09-28: DeepL es un proveedor de paso.** Desde julio de 2026 DeepL
ya no da de alta cuentas en su API gratuita permanente (500 000 caracteres/mes); el
usuario ha abierto una cuenta con cupo limitado "para ir tirando". Traducir la
biblioteca entera son unos **6 M de caracteres** (162 películas, mediana de 34 000
cada una), así que el diseño debe permitir cambiar de proveedor sin tocar nada más:

- El proveedor activo se elige por configuración (`TRANSLATION_PROVIDER=deepl` en el
  `.env`), y cada proveedor lee su propia clave (`DEEPL_API_KEY`, y en el futuro
  `AZURE_TRANSLATOR_KEY` + región, `GOOGLE_…`).
- Nada fuera de `services/translation/` conoce a DeepL: el servicio de trabajos solo
  ve el `Protocol` `Translator`, y el nombre del proveedor queda en
  `translation_job.proveedor`.
- Candidato natural para el relevo: **Azure Translator**, cuyo plan gratuito (F0) da
  2 M de caracteres al mes. Añadirlo es un fichero nuevo en `translation/` más una
  entrada en el registro.

**Invariante que deben respetar las dos fuentes de coreano** (proveedor y alineador):
devuelven exactamente un texto por bloque de origen y en el mismo orden. Es lo que
permite recomponer los bloques sin perder el emparejamiento, y se verifica en el
servicio: no se confía en quien lo produce.

### 6. Generación bilingüe

`app/services/bilingual.py`, **uno solo para los dos modos**:

- `generar(bloques_origen, textos_coreano, ruta_destino) -> Path`, donde
  `textos_coreano` viene de DeepL o del alineador. El generador no sabe ni le importa
  cuál. **Recibe bloques y no la ruta de un `.srt`** (cambio del 2026-09-28): en la
  Fase 5 el origen y el coreano podrán ser pistas extraídas de un MKV, y el usuario
  quiere fusionarlas con este mismo camino dejando el bilingüe fuera, como `.srt`.
  Quien llame (el trabajo) decide de dónde salen los bloques y adónde va el fichero.
- Reconstruye cada bloque como `contenido_original + "\n" + coreano`, **reutilizando
  `indice`, `inicio` y `fin` del bloque original sin tocarlos**. Ese es el punto
  entero del proyecto. Un bloque sin coreano (fusión) se queda solo con el original.
- Escribe con `srt.compose` en UTF-8.
- **Escritura atómica**: a un fichero temporal en el mismo directorio, renombrando al
  final. Así un fallo a medias no deja un `.bilingue.srt` truncado que el siguiente
  escaneo interpretaría como "ya traducido".

### 7. Dónde se escribe el bilingüe

Con la escritura ya disponible en el recurso, se mantiene la convención prevista:
junto al original, `<base>.<ORIGEN>-KO.bilingue.srt`. Dos ajustes:

- Si el origen está en `Subs\`, el bilingüe se escribe **en la carpeta de la obra** (el
  padre) y con la base del **vídeo** de la obra, no la del subtítulo. Es donde Plex lo
  busca, y evita nombres como `English.EN-KO.bilingue.srt`.
- Hecho en el hito 7: `naming.ruta_bilingue_de_obra`. Queda para el hito 8 que el
  escáner detecte el bilingüe al nivel de obra (hoy lo busca junto al subtítulo, y
  no vería el de un origen en `Subs\`).
- Nueva opción `OUTPUT_DIR` en `config.py`, vacía por defecto. Si se rellena, los
  bilingües van ahí replicando la estructura relativa. Queda como red de seguridad por
  si otro recurso vuelve a ser de solo lectura; **no es el camino por defecto**.

**A verificar en Plex (hito 9):** cómo muestra Plex `…ES-KO.bilingue.srt`. Como el
último token antes de `.srt` no es un código de idioma, puede listarlo como idioma
desconocido. Si molesta, el sufijo se ajusta en `naming.py` sin tocar nada más.

### 8. Trabajos

Nueva tabla `translation_job` (`app/models/translation_job.py`):

| Columna | Para qué |
|---|---|
| `id` | PK |
| `subtitulo_id` | FK a `subtitle_file` (el origen ES/EN) |
| `modo` | `TRADUCCION` / `FUSION` |
| `subtitulo_coreano_id` | FK a `subtitle_file`, solo en `FUSION` |
| `estado` | `QUEUED` / `RUNNING` / `DONE` / `FAILED` |
| `proveedor` | Proveedor usado; vacío en `FUSION` |
| `idioma_origen` | `ES` o `EN` (el destino siempre es `KO`) |
| `num_caracteres` | Caracteres enviados a traducir; `0` en `FUSION` — alimenta la Fase 4 |
| `calidad_alineacion` | Solo en `FUSION`, para diagnóstico |
| `bloques_totales`, `bloques_procesados` | Progreso para la barra del front |
| `mensaje_error` | Diagnóstico si falla |
| `creado_en`, `finalizado_en` | Duración |

Nuevos enums `ModoTrabajo` y `EstadoTrabajo` en `models/enums.py`.

**Ajustes al implementar (hito 5):** las dos FKs son `ON DELETE SET NULL` y el
trabajo guarda **copia** de `ruta_origen`, `ruta_coreano` y `ruta_bilingue`. Motivo:
el trabajo es historial (Fase 4) y no debe desaparecer si un escaneo borra su `.srt`,
y en la Fase 5 el origen podrá ser una pista de MKV, que no es una fila de
`subtitle_file`. Se añade `iniciado_en`. No se guarda `idioma_destino`: es siempre
`KO`.

La ejecución va en `BackgroundTasks` de FastAPI, como decidido en CLAUDE.md. Detalle
importante: la tarea de fondo **abre su propia sesión de base de datos**, porque la
sesión inyectada por `get_db` se cierra cuando la petición HTTP responde.

### 9. API

| Endpoint | Qué hace |
|---|---|
| `GET /subtitles/{id}/candidatos` | Candidatos de la obra con su motivo de descarte, coreano disponible y calidad de alineación (se calcula al vuelo: no gasta cuota) |
| `POST /translate` | Encola una o varias obras. Cuerpo: `subtitulo_ids` (origen) y `forzar_traduccion` opcional. El modo se decide solo: fusión si hay coreano con buena alineación, traducción en otro caso |
| `GET /translate/jobs` | Lista de trabajos, filtrable por estado |
| `GET /translate/jobs/{id}` | Estado y progreso de un trabajo |
| `GET /renombrado/propuestas` | Propuestas de renombrado a nomenclatura Plex |
| `POST /renombrado` | Aplica las propuestas confirmadas (lista de ids) |

(Cambio del hito 8: `/renombrado` en vez de `/subtitles/renombrado`, que chocaba con
`/subtitles/{subtitulo_id}`. Además, una fusión de mala calidad no cae en traducción
automáticamente: el trabajo falla y el usuario decide con `forzar_traduccion`.)

`POST /translate` devuelve `202` con los trabajos creados; no espera a que terminen.
Rechaza las obras `SIN_ORIGEN`.

### 10. Frontend

- `ArbolSubtitulos.tsx`: casilla de selección por hoja, estado `SIN_ORIGEN` visible,
  indicador de coreano disponible y botón **Generar bilingües**.
- Nuevo `PanelTrabajos.tsx`: trabajos en curso con su barra de progreso y su modo,
  sondeando `GET /translate/jobs` mientras haya alguno activo.
- Nuevo `SelectorOrigen.tsx`: al desplegar una hoja, muestra el candidato propuesto y
  permite elegir otro de la lista, con el motivo del descarte a la vista. Si la
  alineación del coreano es mala, lo dice y ofrece traducir.
- Nuevo `PanelRenombrado.tsx`: lista `actual → nuevo` con casillas y botón de aplicar.
- `types.ts` y `api/client.ts`: espejo de los DTOs nuevos.

**Sustituido por el rediseño (2026-09-28).** Al usuario no le convencía la interfaz
de la Fase 2 (ni el aspecto ni la organización), así que antes del hito 9 se hizo una
sesión de diseño con maquetas en un lienzo de diseño de claude.ai (privado del
usuario): https://claude.ai/artifact/7P5AmF9e2dkVyxrmxb2o64. Diseño **aprobado**; el
hito 9 lo implementa en React:

- **Estilo**: oscuro, tipo Plex. Tipografías Bricolage Grotesque (títulos), Figtree
  (texto) y Noto Sans KR (coreano). Dos colores con significado: naranja `#FF9A5A`
  para el idioma de origen y azul `#8CC4FF` para el coreano.
- **Cabecera**: pestañas Biblioteca · Trabajos · Renombrar para Plex, indicador del
  trabajo en curso y del cupo libre.
- **Biblioteca en tres columnas**:
  - izquierda, un **árbol de carpetas** (Pelis, Series, Anime) desplegable hasta la
    temporada, **plegable** a una tira estrecha sin perder la selección;
  - centro, el contenido de la carpeta, con filtros por estado y un selector
    **mosaico / lista** que cada carpeta recuerda (películas en mosaico, episodios en
    lista);
  - derecha, el **panel de detalle** de la obra: origen y coreano propuestos (con
    "Cambiar"), calidad de la fusión, vista previa del bilingüe y "Generar".
- **Selección múltiple**: con el modo selección activo, el panel derecho resume lo
  elegido: modo de cada obra, caracteres a enviar y cupo que quedará.
- **Trabajos**: "necesitan tu decisión" (p. ej. una fusión que no casa → descartar o
  traducir), en curso con progreso, historial y cupo.
- **Renombrar para Plex**: tabla `actual → nuevo` con el sufijo resaltado, motivo,
  conflictos desmarcados y barra de aplicar.
- **Carpetas y escaneo** (desde "Gestionar carpetas" en el pie del árbol):
  interruptor de incluir al escanear, escanear o quitar cada carpeta, resultado del
  último escaneo y explorador para añadir.
- **Móvil**: navegación por niveles en vez del árbol y detalle en hoja inferior.
- Los pósteres son marcadores de color con el título; traer los pósteres reales (de
  Plex, por ejemplo) queda como mejora aparte.
- Los MKV (Anime, Series) se ven en el árbol con sus pistas, pero sus acciones quedan
  desactivadas con "Fase 5".

---

## Modelo de datos — cambios

1. `translation_job`: tabla nueva.
2. `subtitle_file`: añadir `es_forzado` y `es_sdh` (booleanos, derivados del nombre en
   el escaneo) para no tener que re-inspeccionar el nombre al puntuar candidatos, y
   `version_analisis`. **Hecho en el hito 1**, con su propia migración
   (`6f170d42eb87`).
3. `docs/modelo-datos.md` y su `.html` se actualizan **en el mismo commit que la
   migración**, como manda su propia regla.

Migración: `uv run alembic revision --autogenerate -m "trabajos de traduccion"`,
revisando lo generado antes de aplicar.

---

## Orden de trabajo

| Hito | Contenido | Verificable por |
|---|---|---|
| **1** | Detección de idioma ampliada (nombre + contenido ES/EN/KO) y flags `forced`/`sdh` | Tests; re-escaneo de `Z:\Pelis` sube de 122 a ~170 obras con origen; *The Wailing* no pasa por coreano |
| **2** | Selección de origen + estado `SIN_ORIGEN` | Tests con los casos reales (*Mercy*, *Jojo Rabbit*, *Bugonia*) |
| **3** | Renombrado Plex (servicio + propuesta) | Tests en carpeta temporal; propuesta sobre `Z:\Pelis` revisada con el usuario **antes** de aplicar nada |
| **4** | Alineación (modo fusión) | Tests con casos sintéticos (1:1, desfase, velocidad, segmentación distinta); calidad medida sobre las ~10 obras reales con ES/EN + KO |
| **5** | Migración + modelo `translation_job` | `alembic upgrade head` y tests de modelo |
| **6** | `Translator` + DeepL + `registry` | Tests con proveedor falso; una llamada real de humo |
| **7** | `bilingual.py` | Test de que los tiempos del bilingüe son idénticos a los del original, en los dos modos |
| **8** | API de trabajos y renombrado | Tests de API |
| **9** | Frontend | Verificación e2e: una fusión (p. ej. *Jaws*) y una traducción reales, vistas en Plex |
| **10** | Documentación: bitácora, `modelo-datos`, READMEs | — |

Los hitos 1 a 4 **se verifican contra la biblioteca real sin gastar un solo carácter
de cuota**, porque no llaman a ningún proveedor. Conviene cerrarlos antes de tocar
DeepL.

---

## Tests

Los 88 actuales deben seguir en verde. Se añaden:

- `test_srt_parser.py`: patrón RARBG, flags entre paréntesis, detección por contenido
  ES/EN/KO y el caso `INCIERTO`.
- `test_seleccion.py`: los casos reales del sondeo, incluido el forzado encubierto por
  ratio de bloques y la obra sin origen.
- `test_renombrado.py`: nombre propuesto, conflicto con fichero existente (no
  sobrescribe), exclusión de `Subs\` y de obras con varios vídeos.
- `test_alineacion.py`: vía 1:1, desfase constante, cambio de velocidad, segmentación
  distinta (el caso *Jaws*) y coreano de otra versión (calidad baja).
- `test_bilingual.py`: tiempos e índices preservados en los dos modos; escritura
  atómica.
- `test_translate_api.py`: encolado, elección de modo, rechazo de `SIN_ORIGEN`,
  progreso y fallo del proveedor.
- Proveedor falso en `conftest.py`, para que **ningún test llame a DeepL**.

---

## Riesgos y cosas a vigilar

1. **Cuota de DeepL.** Medido sobre la biblioteca real: mediana de 34 000 caracteres
   por película, máximo de 98 000. La cuenta de DeepL del usuario tiene cupo limitado
   y caduca (ver el cambio en el punto 4 del diseño). El hito 6 debe probarse con un
   fichero corto, no con una película entera. La fusión, que no gasta
   cuota, se prioriza siempre que haya coreano.
2. **No hay `.env` todavía** (solo `.env.example`) ni clave de DeepL configurada. Hace
   falta crearlo antes del hito 6.
3. **Renombrar ficheros de la biblioteca compartida** no tiene deshacer automático.
   Por eso va en dos pasos con confirmación y nunca sobrescribe.
4. **Umbral de calidad de la alineación.** Se calibra con pocas obras (~10); si más
   adelante aparecen casos límite, se revisa con datos, no a ojo.
5. **Coreano y ancho de línea.** El texto coreano ocupa distinto en pantalla; si las
   líneas quedan largas habrá que decidir si se parten. Eso se ve verificando en Plex,
   no antes.
6. **`Z:` es una unidad de red.** Escribir 176 ficheros sobre SMB es más lento y más
   frágil que en local; de ahí la escritura atómica del punto 6 del diseño.
