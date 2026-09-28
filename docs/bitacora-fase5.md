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

Commit `5bd0058`.

## Hito 5 — Documentación, y paneles redimensionables (2026-09-28)

### Paneles redimensionables (petición del usuario)

El árbol de la izquierda y el panel de la obra de la derecha se ensanchan o
estrechan arrastrando su borde:

- `components/biblioteca/Tirador.tsx`: una franja de 9 px sobre el borde del panel,
  invisible hasta pasar por encima. *Pointer events* con `setPointerCapture`, así
  que vale para ratón, dedo y lápiz, y no se pierde al arrastrar deprisa. Es un
  `separator` accesible: con Tab y las flechas (16 px, ×4 con Mayúsculas),
  Inicio/Fin a los límites, y doble clic para el ancho de siempre.
- Límites: árbol 200–600 px y panel 320–760 px, y nunca por debajo de 320 px para
  el centro (se recalcula al cambiar la ventana, sin perder el ancho elegido).
- Los anchos se guardan en `localStorage` como el resto de preferencias, y llegan
  al CSS como variables (`--ancho-arbol`, `--ancho-panel`). En pantalla estrecha,
  donde los laterales son cajones, no hay tiradores y los anchos se ignoran.
- Un detalle que salió al probarlo: tras arrastrar con el ratón, el tirador quedaba
  enfocado y Chrome lo pintaba como foco de teclado, resaltado hasta hacer clic en
  otro sitio. Se le quita el foco al soltar.

Verificado en el navegador: árbol 284 → 434 px, panel 380 → 580 px; empujando el
panel al máximo, el centro se queda en ~320 px; el ancho sobrevive a recargar; el
doble clic vuelve a 284; dos flechas, +32 px; en móvil no aparece ningún tirador.
Sin errores en consola.

### Documentación

- `README.md` de la raíz: los subtítulos dentro de los vídeos en la descripción,
  ffmpeg como requisito, `FFPROBE_PATH`/`FFMPEG_PATH`/`CACHE_DIR`, el primer uso con
  pistas y los paneles, y el estado de la fase.
- `backend/README.md` y `frontend/README.md`: estructura, ideas de diseño y
  endpoints nuevos.
- `CLAUDE.md`: stack, estado de la Fase 5 y deuda técnica (estado en memoria del
  proceso, el resumen del escaneo sin pistas, el OCR pendiente).
- `docs/modelo-datos.md`/`.html` ya se actualizaron en cada hito.

### Lo que queda de la fase

- **Hito 6: la prueba de calidad** (ver el plan): *Moonrise* 01, fusión con la pista
  `NF_Korean` (ya hecha) frente a traducción con Azure del español, comparadas bloque
  a bloque. Antes, el bilingüe de la fusión se renombra con el sufijo `fusion`.
- Los bilingües de las pruebas (*Moonrise* 01–03, *Shingeki* 01) están en el NAS,
  por si se quieren ver en Plex.

Commit `c4735b0`.

## Hito 6 — Prueba de calidad: fusión frente a traducción (2026-09-28)

### Cómo se hizo

*Moonrise* 01, el mismo origen (pista 7, `NF_Spanish`, 292 bloques), dos coreanos:

- **Fusión** con la pista `NF_Korean` de Netflix: hecha por humanos, sin ninguna API
  nuestra. Calidad de alineación 1,0. Renombrada a `….ES-KO.bilingue.fusion.srt`
  (idea del usuario) para que no la pisara la otra.
- **Traducción** con Azure, forzada (`forzar_traduccion`): 7.966 caracteres, 3 s.

Los dos bilingües comparten tiempos, así que se compararon bloque a bloque, los 292
(Claude, leyendo el español y los dos coreanos).

### Cifras

| | Netflix (fusión) | Azure (traducción) |
|---|---|---|
| Coreano idéntico al otro (sin espacios) | 20 bloques | 20 bloques |
| Longitud media del coreano | **11,3** caracteres | 14,4 caracteres (+27 %) |
| Líneas con terminación formal (`요`/`니다`) | 23 | **65** |
| Líneas con el sentido equivocado o roto | casi ninguna¹ | **~55–60 (≈20 %)** |

¹ Ver «Matiz» abajo: a veces dice otra cosa que el español, pero no por error.

### Lo que falla en Azure, por orden de peso

1. **Frases partidas en dos líneas.** 58 de los 292 bloques traen el español en dos
   líneas, y Azure traduce cada línea como si fuera una frase suelta. Es la causa
   principal de los errores graves:
   - «Concluyen ya los festejos por el proyecto / del eje orbital de Sapientia» →
     «프로젝트 축하 행사는 이제 끝났습니다 / 사피엔티아 궤도 축에 위치해 있다» (dos
     frases que no casan).
   - «Noventa segundos / para atracar en el Eje Orbital E40» → «90초 / E40 궤도 축에
     도킹하기 위해서였다».
   - «te lo tomas todo a la ligera / y eres irresponsable» → «너는 이 모든 걸
     가볍게 받아들이지 마 / 그리고 당신은 무책임해요»: el sentido **se invierte**
     («no te lo tomes a la ligera») y cambia de registro a media frase.
   También pasa entre bloques (una frase que sigue en el bloque siguiente), pero eso
   es menos frecuente.
2. **Coloquialismos traducidos al pie de la letra.**
   - «¡Menudo inepto enchufado!» → «정말 서투른 연결고리네요!» («¡qué eslabón torpe!»);
     Netflix: «그 금수저 한량 아들 말이군».
   - «no puedes (ser) más estirado» → «이보다 더 스트레칭될 수 없어» (de estirar un
     músculo); Netflix: «너는 진짜 딱딱하구나».
   - «Hay que salir pitando» → «이제 휘파람 불고 나가야 해» (silbando).
   - «me las pagarás» → «그것들에 대해 돈을 지불해야 합니다» (pagar dinero).
   - «Hala, qué pasada» → «할라, 정말 신나네요» (transcribe «Hala»); «Jo, que Jack
     está aquí» → «조, 잭이 왔어» (toma «Jo» por un nombre); «¡Largo!» → «롱!»; «Oye,
     Phil» → «안녕, 필» («hola»); «¡Anda! ¡Pero si es un Eber!» → «어서! 하지만 이건
     에버야!».
3. **Registro sin coherencia.** Traduciendo línea a línea no sabe quién habla a
   quién: pasa de tutear a tratar de usted dentro de la misma escena (a la hermana,
   «언니, 어떻게 지내세요?»; en pleno combate, «E2 자료를 낭비하지 마세요!»). Casi el
   triple de terminaciones formales que Netflix.
4. **Términos de la serie.** El título «Rebelión lunar» sale como «달의 반란» (Netflix
   usa el oficial, «문라이즈»); «rollo de carne» como «고기 롤» (es meatloaf,
   «미트로프»); «Aplicar grabado» como «각인을 적용하세요» (en la serie es el comando
   «인그레이브 실행»); «Capitán» como «선장님» (de barco; es militar, «대장님»);
   «órbita de estacionamiento» como «주차 궤도» (de aparcar).
5. **Más largo.** Netflix condensa para que dé tiempo a leer («No hay tiempo para
   arreglarlo» → «수리할 시간 없어»); Azure traduce todo, con terminaciones largas.

**Lo que Azure hace bien**: las frases cortas y directas, que son muchas («¿Estás
bien?» → «괜찮아?», «¡Corred!» → «도망쳐!», «Mierda» → «젠장», los nombres propios).
Una escena de diálogo rápido se sigue sin problema.

### Matiz: el coreano de Netflix no es traducción del español

Los dos subtítulos de Netflix están traducidos **del japonés**, no el uno del otro.
Por eso la fusión a veces dice otra cosa que el español del mismo bloque («Toca
defenderse» / «집중 좀 할게», «me concentro»), y a veces reparte la información de otra
manera entre dos bloques seguidos: en «También quisiera aprovechar la oportunidad /
para presentarles a mi hijo» + «Tras graduarse en la universidad, será miembro del
consejo», el coreano pone el «tras graduarse» en el primero y el «presentarles a mi
hijo» en el segundo, que es el orden natural en coreano. Para ver la serie no molesta
(los dos dicen lo que dice el original); para estudiar comparando línea a línea, hay
que saberlo.

### Conclusiones

1. **Cuando hay coreano de verdad, la fusión es claramente mejor**: natural, con el
   registro de cada personaje, los términos oficiales y líneas más cortas. Confirma la
   regla que ya aplica la app (fusión antes que traducción), y que las 59 obras con
   coreano en texto de la biblioteca son lo primero que conviene generar.
2. **La traducción de Azure sirve para seguir la serie, no para estudiar coreano**:
   se entiende en la mayoría de líneas, pero uno de cada cinco bloques está mal o roto,
   y el registro no es fiable.
3. **Hay una mejora barata y con mucho efecto**: unir las líneas de cada bloque en una
   sola frase antes de enviarla al proveedor (y repartir el coreano en dos líneas al
   escribir el bilingüe). El usuario la aprobó: ver la segunda ronda.

### Segunda ronda: la mejora, y DeepL (2026-09-28)

A petición del usuario, en este orden: guardar la traducción de Azure de la primera
ronda, hacer la mejora, traducir otra vez con Azure y luego con DeepL, y comparar las
cuatro versiones.

**La mejora** (`services/subtitles/lineas.py`, en todos los proveedores): las líneas
de un bloque se envían unidas en una frase, y el coreano vuelve en dos líneas (por el
espacio más cercano al centro) si el original venía en dos y el coreano pasa de 18
caracteres. Los **diálogos** (una línea por personaje, con guion: 20 bloques en el
episodio) se envían como estaban, para no juntar dos voces. 15 tests nuevos.

**Coste**: 7.966 caracteres cada traducción (Azure, 3 s; DeepL, 6 s).

| | Netflix (fusión) | Azure antes | Azure después | DeepL (con la mejora) |
|---|---|---|---|---|
| Líneas mal o rotas (a ojo, 292) | casi ninguna | ~55–60 (≈20 %) | **~45 (≈15 %)** | **~30 (≈10 %)** |
| Longitud media del coreano | 11,0 | 14,0 | 13,6 | 15,0 |
| Líneas en registro formal | 23 | 65 | 65 | **91** |
| Nombres propios coherentes | sí | sí | casi (1 fallo) | **no** |

**Azure después de la mejora.** Los bloques de frase partida, que eran lo peor, quedan
casi todos bien. «te lo tomas todo a la ligera / y eres irresponsable», que salía con
el sentido invertido, queda «당신은 모든 걸 가볍게 / 여기고 무책임해요» (correcto,
aunque en «당신»). «Noventa segundos / para atracar…» queda «E40 궤도축에 도킹까지 /
90초 남았습니다». Las líneas de una sola línea salen idénticas a la primera ronda
(Azure es determinista): siguen los calcos («연결고리», «스트레칭», «휘파람»). Un fallo
nuevo: «Shadow Corporation» traducido como «그림자 회사» («empresa sombra») en un bloque.
El corte por el centro a veces cae en mitad de un sintagma («에피소드 1 모든 / 것이…»).

**DeepL.** El que mejor entiende el español coloquial, justo donde Azure fallaba:
«inepto enchufado» → «무능한 빽 있는 놈», «estirado» → «뻣뻣해질», «salir pitando» →
«당장 서둘러 나가야 해», «Hala, qué pasada» → «와, 진짜 대박이네», «¡Largo!» →
«물러나라!», «Jo, que Jack está aquí» → «야, 잭이 왔어». Sus fallos son otros:

- **Registro**: el más formal de todos (91 líneas con `요`/`니다`), y cambia de uno a
  otro en el mismo personaje («전 전혀 모르겠어요» justo después de «내가 뭘 알겠어»).
- **Nombres incoherentes dentro del mismo episodio**: «게오르크», «게오르그» y
  «조르그» para el mismo personaje; «사피엔티아», «사피엔시아» y «Sapientia» para la IA;
  «코페르니코» (del español) en vez de «코페르니쿠스»; «Whiz» sin transcribir.
- **Sin contexto**: «¿Cómo está?», dicho de un herido, → «잘 지내시나요?» («¿qué tal
  le va?»); «Hermana» → «자매님» (monja); «¡Que me contestes!» → «답장 좀 해줘»
  (conteste un mensaje); «Ay, madre…» → «아이고, 엄마…».
- Las líneas más largas (15,0 de media).

### Conclusiones de la prueba

1. **Orden de calidad: fusión con coreano de verdad ≫ DeepL > Azure con la mejora >
   Azure antes.** La fusión sigue sin rival y confirma la regla de la app.
2. **La mejora compensa**: Azure baja de ≈20 % a ≈15 % de líneas mal, sin gastar un
   carácter más, y beneficia igual a DeepL. Se queda.
3. **DeepL traduce mejor que Azure**, sobre todo lo coloquial, pero su cupo es un
   millón de caracteres **en total** (unos 125 episodios), frente a los 2 millones
   **al mes** de Azure. Con `TRANSLATION_PROVIDERS=azure,deepl`, DeepL solo entra
   cuando Azure se queda sin cupo. Invertir el orden, o poder elegir proveedor por
   obra desde la interfaz, lo decide el usuario.
4. **Lo que les falta a los dos** (y a la app) es **contexto**: cada bloque se traduce
   solo. De ahí el registro errático y los nombres cambiantes. Mejoras posibles, por
   orden de coste:
   - cortar el coreano en dos líneas preferiblemente tras un signo de puntuación,
     no solo por el centro;
   - un glosario de la obra (nombres propios fijos), si el proveedor lo admite para
     ES→KO;
   - enviar el bloque anterior como contexto.

**Decisión del usuario sobre el punto 3**: poder **elegir el proveedor por obra**
desde la interfaz (ver abajo), manteniendo el orden automático por defecto.

**Ficheros**: junto al vídeo se queda **el de la fusión**, con su nombre normal (el
que ve Plex), por decisión del usuario. Las tres traducciones de prueba se guardaron
fuera de la biblioteca (carpeta de trabajo de la sesión). Los 3 × 7.966 caracteres
gastados (2 de Azure y 1 de DeepL) se registraron en la copia de la base de datos,
no en la de desarrollo. El de DeepL sí se ve en su cupo real, porque DeepL lo informa
por API.

### Elegir el proveedor por obra (petición del usuario, tras la prueba)

- **Interfaz**: en el detalle de una obra que se va a traducir (sin coreano, o con
  uno que no casa), «Traducir con: **Automático** · Azure · DeepL», con el cupo libre
  de cada uno. Automático indica cuál elegiría la app. Los que no pueden (sin clave, o
  sin cupo para esa obra) salen desactivados con el motivo. En una obra que se
  fusiona no aparece. Lo elegido se olvida al cambiar de obra.
- **Backend**: `POST /translate` ya aceptaba `proveedor`, pero se lo saltaba todo: un
  proveedor sin clave o sin cupo creaba un trabajo que fallaba al ejecutarse. Ahora
  pasa por la misma regla que la elección automática (`Asignador.asignar(…, solo=)`):
  si no puede, la obra va a los rechazos con el motivo, sin probar con otro (el
  usuario eligió ese).
- `utils/cupos.ts` gana `cabe()`, la regla de cupo que comparten la previsión y el
  selector.
- Tests: 6 nuevos (319). En el navegador, interceptando la petición para no gastar
  cupo: con DeepL elegido, «Se traducirá con DeepL» y `"proveedor": "deepl"` en la
  petición; en automático, `null`; en una obra con fusión, sin selector.

Commit `10578cb`.

## Cierre de la fase (2026-09-28)

### Lo que deja la Fase 5

- **Los subtítulos de dentro de los vídeos, utilizables**: en Anime, 207 obras
  elegibles que antes salían «sin subtítulos», 27 de ellas fusionables sin gastar
  cupo. En toda la biblioteca: 278 MKV con origen ES/EN en texto y 59 con coreano.
- **Los tres casos que pidió el usuario**: fusión pista + pista, pista + `.srt`
  coreano externo, y traducción de una pista. El bilingüe siempre como `.srt` junto
  al vídeo; el vídeo no se toca.
- **Una prueba de calidad** que ordena las fuentes del coreano (fusión ≫ DeepL >
  Azure) y una mejora aplicada a todas las traducciones (las líneas de un bloque se
  traducen unidas).
- **En la interfaz**: pistas «dentro del vídeo», extracción bajo demanda, la fase
  «Extrayendo», la lectura de pistas tras escanear, el proveedor por obra y los
  paneles laterales redimensionables.
- **319 tests** (227 al empezar la fase). Migraciones nuevas: `c3a9e5f17b20` (pistas
  incrustadas) y `e81d4b0c9a37` (fase de los trabajos).

### Para empezar a usarla con la base de datos de desarrollo

Todas las pruebas se hicieron sobre **una copia** de la base de datos
(`DATABASE_URL` apuntando a la carpeta de trabajo de la sesión). La de desarrollo,
`backend/srt_bilingual.db`, sigue en la migración de la Fase 4. Para usar lo nuevo:

```powershell
cd backend
uv run alembic upgrade head      # aplica las dos migraciones de la fase
uv run uvicorn app.main:app --reload --port 8000
```

y en la interfaz, **Escanear**: la primera lectura de pistas de las tres carpetas son
unos 8 min por la red, en segundo plano.

Consecuencias de haber probado sobre la copia:

- Los caracteres gastados en las pruebas con Azure (6.921 de *Shingeki* 01 y 2 ×
  7.966 de *Moonrise* 01, antes y después de la mejora) **no están en el registro de
  Azure** de la base de datos de desarrollo, que es de donde sale su cupo. Son 22.853
  de 2.000.000, el 1,1 % del mes. DeepL, que informa por API, sí refleja sus 7.966.
- Los bilingües escritos en el NAS (*Moonrise* 01–03, *Shingeki* 01) los reconocerá
  el primer escaneo, como cualquier bilingüe que ya exista en disco.

### Pendiente

- **Mejoras de traducción** (de la prueba de calidad), por orden de coste: cortar el
  coreano por la puntuación y no solo por el centro; glosario de nombres propios por
  obra; enviar el bloque anterior como contexto.
- **OCR** de las pistas de imagen (130 capítulos de Series), si algún día se quiere:
  sería una fase aparte.
- **Despliegue con Docker** (documentación, el NAS aún no existe) y **web de
  documentación**. **Repaso docente**, aplazado.
