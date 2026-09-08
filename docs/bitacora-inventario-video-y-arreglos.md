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
- Los nombres de los ficheros llevan `MultiSub` y `Dual-Audio`, lo que apunta a
  pistas embebidas, pero hasta pasar `ffprobe` no se sabe si son texto o imagen.

## Pendiente

- Sondeo con ffmpeg (`winget install Gyan.FFmpeg`) e informe de las pistas reales.
