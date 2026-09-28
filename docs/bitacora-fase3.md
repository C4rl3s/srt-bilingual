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
