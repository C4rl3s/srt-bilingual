# Bitácora — Glosario por obra (guía de traducción)

Plan: `docs/plans/plan-glosario-por-obra.md`. Referencia humana del caso real:
`docs/glosarios/shingeki-no-kyojin.md`. Todo se hizo el 2026-09-29.

## De dónde sale

La mejora nace de trabajar con *Shingeki no Kyojin* (Anime), temporada a temporada:

- **S1–S2: fusión con un fansub coreano en `.smi`.** El usuario encontró los SMI de
  바보개 (2013) de las dos primeras temporadas. Se convirtieron a `.ko.srt` junto a
  cada vídeo (37 ficheros), quitando las letras de las canciones. Las letras van en
  el mismo `<SYNC>` que el diálogo, como pareja de línea en otro idioma y traducción
  coreana. Además se aplicó el desfase medido contra la pista española del MKV: **S1
  +16,0 a +16,35 s; S2 ±0,4 s**. Calidad de alineación 0,90–0,97 en los 37
  capítulos. Tareas sueltas, sin cambios en la app.
- **S3: `.ko.srt` que trajo el usuario** (22, renombrados por él con el nombre de cada
  vídeo). Revisado solo el 01, por petición suya: desfase 0,00 s y calidad 0,97.
- **S4: sin coreano**, así que se tradujo con DeepL desde la app y se repasó el
  coreano a mano capítulo a capítulo. Del 01 al 06 hubo que corregir **139, 195, 159,
  165, 189 y 140 bloques (40–55 %)**. Del 02 al 06 se repasaron en paralelo, un agente
  por capítulo con el mismo glosario y los mismos criterios; cada lista de cambios se
  revisó antes de aplicarla. Los bilingües corregidos están en el NAS, y los
  originales de DeepL y las listas de cambios en la carpeta temporal de esa sesión.

Casi la mitad de los fallos eran **nombres y términos** (말리, 타이탄, 전함, 화물선,
수술…). El resto: sentido (cada bloque traducido sin ver los demás), registro (반말 y
존댓말 cambiando sin motivo, el *ustedes* latino tomado como formal, diálogo en estilo
narrativo -다) y frases partidas entre bloques.

Primera prueba con el 01, fuera de la app: glosario, instrucciones y contexto
juntos bajaron los bloques con errores **de 139 a ~64**. Destapó dos problemas:
- las instrucciones juntan en una línea los diálogos con guion (comprobado aislando
  cada opción);
- una entrada genérica del glosario («los nueve») convirtió «hace nueve años» en
  «아홉 거인 전부터».

Qué admite cada proveedor (comprobado en su documentación y con la clave del usuario):
- **DeepL:** glosario español → coreano, `custom_instructions` y `context`, este
  último sin coste.
- **Azure:** no tiene glosario español → coreano, porque su diccionario dinámico
  exige inglés en uno de los dos lados.

## Hito 1 — La guía: formato, localización y validación (`b6f38e5`)

- `services/translation/guia.py`: `srt-bilingual.toml` en la carpeta de la serie,
  leído con `tomllib`, sin dependencias nuevas. Se busca subiendo desde la carpeta de
  la obra hasta la raíz de su carpeta de biblioteca, y gana la más cercana.
- **Validación:** TOML roto, secciones desconocidas, valores que no son texto,
  entradas vacías o con tabuladores, más de 10 instrucciones o de 300 caracteres,
  guía vacía.
- `GuiaInvalida` hereda de `ErrorTraduccion`: una guía rota no se ignora en silencio.
- **Cambio sobre el plan:** las variantes de mayúsculas no son duplicados (DeepL
  distingue mayúsculas), y las entradas genéricas no se detectan porque no hay regla
  fiable. Lo explican la plantilla y el README.
- 344 tests.

## Hito 2 — DeepL usa la guía (`afd5055`)

- `Translator.traducir(..., guia=None)` y un atributo `admite_guia`: `True` en DeepL,
  `False` en Azure, que recibe la guía y la ignora.
- **DeepL:**
  - glosario cacheado en la cuenta con nombre `srt-bilingual:<ruta>:<huella>:ES-KO`,
    reutilizado entre procesos; al cambiar la guía se sustituye solo su versión
    anterior, sin tocar las de otras series ni los glosarios ajenos;
  - instrucciones en `custom_instructions`, y con ellas cada línea de un diálogo va
    por separado;
  - con origen inglés, solo instrucciones.
- **Verificado contra DeepL real** (unos 40 caracteres): glosario aplicado, diálogo con
  sus guiones, y reutilización del glosario desde un segundo traductor.
- 357 tests.

## Hito 3 — La guía decide el proveedor y viaja con el trabajo (`2b75453`)

- **Decisión del usuario, que cambia el plan:** buscar la guía de cada obra en disco
  costaba **2,3 s** por carga del árbol (348 carpetas por la red). Así que el escaneo
  la **indexa** en una tabla nueva, `guide_file` (migración `1dad6a0e64cd`), y cada
  hoja del árbol lleva `ruta_guia` sin tocar el disco. El contenido se sigue leyendo
  del disco al crear y al ejecutar el trabajo. Se exige el nombre exacto del fichero,
  porque en el NAS (Linux) leerlo distingue mayúsculas.
- **Elección de proveedor:** si la obra tiene guía, se prefieren los proveedores que la
  admiten, conservando el orden configurado dentro de cada grupo. La misma regla está
  en `eleccion.py` y en `cupos.ts`.
- **El trabajo:**
  - una guía rota rechaza la obra al crear;
  - al ejecutarse, relee la guía, la pasa al traductor y la anota en
    `translation_job.guia` (`<ruta> (<huella>)`) si el proveedor la usó;
  - si al ejecutar la guía está rota, falla con el motivo.
- 376 tests; migración aplicada a la base de datos de desarrollo.

## Hito 4 — La guía en la interfaz (`3a87c69`)

- Los candidatos de la obra incluyen un resumen de la guía: ruta, carpeta, términos,
  instrucciones y error. La localiza el índice, igual que la previsión de proveedor.
- **Panel de la obra**, al traducir: fila «Guía de traducción · Shingeki · N términos
  · M instrucciones», con dos avisos posibles, «Azure no admite glosario» y «con
  origen inglés solo se aplican las instrucciones». Una guía con errores o borrada
  desde el escaneo sale en rojo con el motivo.
- La lista de trabajos marca «· con guía».
- 380 tests.

## Hito 5 — Guía real de Shingeki y verificación (`3a84f75`)

- `Z:\Anime\Shingeki\srt-bilingual.toml`: 140 términos (frases concretas y sus
  variantes), 8 instrucciones de registro y trato, y contexto activado. No está en el
  repo: vive en la biblioteca. Escaneo: `"guias": 1`, y el 07 la resuelve.
- **Prueba A/B sobre el S4 Pt. 1-07** (225 bloques; unos 5.000 caracteres cada
  variante, porque el contexto no se cobra):

  | | A: guía sin contexto (la app) | B: guía + contexto |
  |---|---|---|
  | Bloques con algo que corregir | ~55 (24 %) | **~26 (12 %)** |
  | Términos / sentido / registro | ~9 / ~12 / ~25 | ~8 / ~5 / ~6 |

  El contexto se activa: opción `[opciones] contexto = true`, con 2 bloques vecinos
  por lado calculados por el trabajo sobre el capítulo entero, no por lote. Cuesta una
  petición por bloque: 110 s para el 07.
- **Fallos de formato que salieron en A, y sus arreglos:**
  - «¡피크!»: `lineas.recolocar` quita «¡» y «¿» del coreano, con cualquier
    proveedor;
  - un guion de diálogo perdido: el proveedor lo devuelve;
  - «Para.» → «.», y dos entradas ignoradas por el glosario («¡El titán carguero!» →
    거대한 화물선, «Paradis» → 파라디스): no volvieron a salir con contexto;
  - Ackerman → 애커맨: añadido a la guía.
- **Verificación de extremo a extremo** (el 07 regenerado desde la app con la guía
  final):
  - DeepL elegido aunque Azure va primero en `TRANSLATION_PROVIDERS`;
  - guía anotada en el trabajo;
  - ningún «¡¿», ningún bloque vacío, y los guiones de los diálogos conservados.
- 389 tests.

## Hito 6 — Documentación

README (sección de la guía y estado), `CLAUDE.md` (fase, arquitectura y deuda),
`docs/modelo-datos.md` y `.html` (`guide_file`, `translation_job.guia` y la decisión 9)
y esta bitácora.

## Lo que queda

- **Repasar el 07.** Con guía y contexto quedan unos 25 bloques, frente a los ~140 de
  antes, con fallos que el glosario no resuelve: «¡Oficial!» → 경관님, «Sal, Levi» →
  나가, algún 존댓말 fuera de sitio.
- **Ver el panel en el navegador:** no se pudo desde la sesión. Hay que comprobar la
  fila de la guía en el 07 y el «con guía» en la lista de trabajos.
- **Proteger los bilingües repasados a mano:** regenerar el S4 01–06 desde la
  interfaz pisaría sus correcciones. Fuera de alcance; merece una mejora aparte.
- **Las instrucciones se cumplen a medias**, sobre todo con Magath. El repaso sigue
  haciendo falta, aunque con la mitad o menos de trabajo.
- **La guía no está versionada** en el repo. Si hace falta historial, se puede guardar
  una copia en `docs/glosarios/`, a costa de mantener dos ficheros iguales.
