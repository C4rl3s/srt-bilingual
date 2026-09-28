# Bitácora — Inventario de vídeo, arreglos de la Fase 2 y sondeo MKV

Plan: `docs/plans/plan-inventario-video-y-arreglos.md`.

## Estado: **completado el backend y el frontend** (2026-08-11)

88 tests en verde, `ruff` y `oxlint` limpios, `npm run build` correcto y verificación
contra la biblioteca real. Pendiente: el sondeo de los MKV con ffmpeg, que requiere
instalar software.

## Por qué existe este trabajo

Al levantar la aplicación por primera vez contra la biblioteca real, el árbol salió
vacío y el selector de carpetas se comía dos de los tres recursos compartidos. El
diagnóstico (sondeos de solo lectura) reveló tres cosas:

1. **El árbol vacío no era un bug.** `Z:\Anime` tiene 215 `.mkv` y **cero** `.srt`.
   El árbol se derivaba solo de `subtitle_file`, así que no había nada que dibujar.
2. **El selector sí fallaba**, pero por una causa ajena: `Pelis` y `Series` son
   *junctions* que apuntan a `E:\Videos\...` del otro equipo, fuera del recurso
   compartido. No se pueden abrir desde aquí con ningún programa. Nuestro filtro
   `if not entrada.is_dir(): continue` las ocultaba sin decir nada.
3. **No había ffmpeg**, así que no se podía saber si las pistas embebidas son texto
   o imagen — dato imprescindible para diseñar la Fase 5.

## Implementado

**Inventario de vídeo**

- `EXTENSIONES_VIDEO` en `models/enums.py`; tabla `media_file`
  (`models/media_file.py`) con migración `deb86f77e1a9`.
- `scanner.py`: `_escanear_carpeta` pasa de `rglob("*.srt")` a **un solo recorrido**
  `rglob("*")` que reparte por extensión (la biblioteca está en otro equipo y cada
  pasada cuesta). Los vídeos se registran sin abrirlos. `ResumenEscaneo` gana
  `videos`; huérfanos en las dos tablas.
- `library_tree.py`: el árbol se alimenta de las dos tablas. Hoja = obra, agrupando
  por `(directorio, base_sin_idioma)`. Estado nuevo `EstadoObra`
  (`DUAL`/`PENDIENTE`/`SIN_SUBTITULOS`/`ERROR`) y agregado `num_sin_subtitulos`.
  Con filtro por estado de subtítulo, los vídeos sin `.srt` se omiten: no pueden
  cumplirlo.

**Selector de carpetas**

- `filesystem.py` usa `os.scandir` con `is_dir(follow_symlinks=False)` para listar
  los reparse points, y `EntradaDirectorio` gana `accesible` y `motivo`.
- **Trampa que costó una iteración:** `DirEntry.is_dir()` reutiliza los atributos
  que ya venían en el listado del directorio padre, así que una junction rota
  devuelve `True` **sin llegar a seguirla**. Solo un `stat` nuevo
  (`Path(entrada.path).is_dir()`) revela que no se puede abrir. Queda fijado en
  `test_browse_lista_un_enlace_roto_como_inaccesible`, que crea el enlace con
  `mklink /J` (no exige privilegios, a diferencia de los symlinks).
- El modal pinta las inaccesibles atenuadas, con su motivo y una nota explicando que
  la solución está en el equipo que comparte.

**Estados vacíos** — `App.tsx` distingue sin carpetas / sin escanear / escaneado sin
resultados (mencionando que los subtítulos embebidos aún no se leen) / sin resultados
para el filtro.

**READMEs** — `backend/README.md` y `frontend/README.md` escritos de cero.

## Verificación (2026-08-11)

- `uv run pytest` → **88 passed**. `ruff` y `oxlint` limpios, `npm run build` OK.
- **Contra la biblioteca real** (`\\192.168.1.130\Compartido\Anime`):
  - `POST /scan` → `{carpetas:1, videos:215, total:0}` en **2,2 s**. Inventariar sin
    abrir los ficheros sale muy barato incluso por red.
  - `GET /library/tree` despliega hasta el capítulo: 215 obras, todas
    `SIN_SUBTITULOS` con `tiene_video=true`.
  - `GET /fs/browse` sobre `Z:\` ahora lista `Anime` (accesible) y `Pelis`/`Series`
    marcadas como inaccesibles con su motivo.
  - `base_sin_idioma` comprobada contra los nombres reales: `[Erai-raws] Moonrise -
    01 [1080p NF WEBRip HEVC EAC3][MultiSub][FAB9E30C]` sale igual desde el `.mkv`
    que desde el `.srt`, así que agruparían bien.

## Hallazgos que condicionan las fases siguientes

- **El recurso compartido está montado en solo lectura.** Escribir el `.bilingue.srt`
  junto al original —la convención del proyecto— fallará ahí con
  `UnauthorizedAccessException`. **Bloquea la Fase 3.** Hay que conseguir permiso de
  escritura en el recurso o añadir una carpeta de salida configurable.
- La biblioteca es **toda MKV**: sin la Fase 5 no hay nada que traducir.

## Sondeo de los MKV reales (2026-09-08)

Instalado **ffmpeg 9.0.1** (`winget install Gyan.FFmpeg`) y pasado `ffprobe` a los
**215 ficheros**, no a una muestra. Resultado:

| Métrica | Valor |
|---|---|
| Pistas de subtítulo encontradas | **2388** |
| Códec `ass` (texto) | 1736 |
| Códec `subrip` (texto) | 652 |
| Códecs de imagen (`hdmv_pgs_subtitle`, `dvd_subtitle`) | **0** |
| Ficheros sin ninguna pista | 8 |

**La respuesta a la pregunta que bloqueaba la Fase 5: todo es texto.** Ni un solo
PGS ni VobSub en toda la biblioteca. **No hace falta OCR.**

Los 8 ficheros sin pistas son los NCOP/NCED de Jujutsu Kaisen (aperturas y cierres
sin créditos, sin diálogo): es lo correcto, no un fallo.

Desglose por serie de los ficheros con diálogo (207):

| Serie | Ficheros | Con `spa` | Con `eng` | Con `kor` |
|---|---|---|---|---|
| Shingeki no Kyojin (S1–S4) | 89 | 89 | 89 | 0 |
| Jujutsu Kaisen (S1–S3) | 59 | 59 | 59 | 0 |
| Moonrise | 18 | 18 | 18 | **18** |
| Lazarus | 13 | 13 | 13 | 0 |
| Kaiju No. 8 (S2) | 12 | 12 | 12 | 0 |
| PLUTO | 8 | 8 | 8 | **8** |
| Gunbuster | 6 | 6 | 6 | 0 |
| JoJo — Steel Ball Run | 1 | 1 | 1 | **1** |
| Rooster Fighter | 1 | 0 | 1 | 0 |

**27 ficheros ya traen pista coreana**, todos de origen Netflix (`NF_Korean`). Para
esos el objetivo del proyecto se cumple **sin traducir ni un carácter**: basta
extraer las dos pistas y fusionarlas reutilizando los tiempos.

### Consecuencias para el plan

1. **La Fase 5 se abarata mucho y merece adelantarse a la Fase 3.** Sin OCR, extraer
   es un `mkvextract`/`ffmpeg` y el `.srt` resultante ya entra en el pipeline actual.
   Con la biblioteca real siendo 100 % MKV, la Fase 3 hoy no tiene nada sobre lo que
   trabajar.
2. **Camino sin coste de API**: para los 27 ficheros con coreano, extraer + fusionar.
   No consume cuota de DeepL. Conviene que el generador de bilingües acepte una pista
   ya existente como "traducción", no solo la salida de un proveedor.
3. **La selección de pista no es trivial** y es donde estará el trabajo real: conviven
   `Forced` (solo carteles), `SDH`/`CC` (con descripciones sonoras), `[Signs]`,
   variantes regionales (`European` vs `Latin American`) y hasta dos pistas del mismo
   idioma sin distintivo. Elegir la equivocada da un bilingüe inservible.
4. **ASS → SRT pierde información**: 1736 de las 2388 pistas son ASS, con estilos y
   posicionamiento. `ffmpeg` convierte, pero los carteles posicionados se mezclarían
   con el diálogo en el `.srt` plano. Hay que decidir si se descartan las líneas de
   cartel o se aceptan.

## Cierre (2026-09-27): los dos pendientes, resueltos

Quedaban abiertas dos cosas. Ambas se resolvieron al conceder el acceso completo al
recurso compartido.

**1. Dónde se escribe el `.bilingue.srt`.** Ya no hay que decidir nada: el recurso
**acepta escritura**. Comprobado creando y borrando un fichero de prueba en
`Z:\Anime`, `Z:\Pelis` y `Z:\Series`; las tres responden `ESCRITURA OK`. Se mantiene
la convención original de dejar el bilingüe junto al original. La carpeta de salida
configurable se conserva en el plan de la Fase 3, pero degradada a red de seguridad
en vez de camino principal.

**2. El orden de las fases.** La recomendación del 08-09 era adelantar la Fase 5 a la
3, y **se revierte**. Nació de que la única carpeta visible era `Anime`, 100 % MKV sin
un solo `.srt`: sin extracción no había nada que traducir. Con `Pelis` y `Series`
accesibles, el cuadro es otro:

| Carpeta | `.mkv` | `.mp4` / `.avi` | `.srt` |
|---|---|---|---|
| Anime | 215 | 0 | 0 |
| Series | 184 | 0 | 0 |
| **Pelis** | 29 | 196 | **686** |

Los 686 `.srt` de `Pelis`, repartidos en 176 carpetas de película, le dan a la Fase 3
banco de pruebas propio. **Se recupera el orden original del plan.**

Nota sobre las *junctions*: `Anime`, `Pelis` y `Series` siguen siendo enlaces al disco
del otro equipo, pero ahora se recorren sin problema desde aquí. La suposición de que
un *junction* fuera del recurso era intransitable por definición era incorrecta: lo
que fallaba eran los permisos, no el enlace.

El sondeo de los `.srt` reales de `Pelis` —que no son ni de lejos uniformes— y lo que
obliga a añadir a la Fase 3 está en `docs/plans/plan-fase3.md`.
