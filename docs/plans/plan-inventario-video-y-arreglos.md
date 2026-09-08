# Inventario de vídeo, arreglos de la Fase 2 y sondeo MKV

## Contexto

Al levantar la aplicación por primera vez contra la biblioteca real aparecieron dos
problemas y un hallazgo que cambia las prioridades del proyecto.

**Diagnóstico realizado (2026-08-11), con sondeos de solo lectura:**

1. **El árbol vacío no era un bug.** `Z:\Anime` tiene **215 ficheros `.mkv` y cero
   `.srt`**: los subtítulos van embebidos. El escaneo hizo lo correcto (registró
   `ultimo_escaneo`, encontró 0 ficheros) y el árbol, que se deriva de
   `subtitle_file`, no tenía nada que dibujar. La app no puede hacer nada útil con
   esta biblioteca hasta la Fase 5.
2. **El selector sí falla.** `Anime`, `Pelis` y `Series` son *junctions* dentro de
   `\\192.168.1.130\Compartido`. Desde este PC:

   | Recurso | `is_dir()` | `iterdir()` |
   |---|---|---|
   | `Anime` | `True` | 11 subcarpetas, OK |
   | `Pelis` | `False` | `PermissionError [WinError 5]` |
   | `Series` | `False` | `PermissionError [WinError 5]` |

   Apuntan a `E:\Videos\...` del otro PC, fuera del recurso compartido, así que
   Windows no las puede seguir desde aquí — **con ningún programa**, no solo con el
   nuestro. Lo que sí es culpa nuestra es que `if not entrada.is_dir(): continue`
   las oculte en silencio.
3. **No hay `ffmpeg` ni `mkvtoolnix` instalados**, así que aún no sabemos si las
   pistas embebidas son texto (SRT/ASS, traducibles) o imagen (PGS/VobSub, que
   exigirían OCR). Sin ese dato, diseñar la Fase 5 entera sería adivinar.

**Objetivo de este plan:** dejar la aplicación útil y honesta sobre una biblioteca de
vídeo —mostrando la estructura real y marcando qué no tiene subtítulos—, arreglar el
selector, saldar la deuda de los README, y **averiguar con datos** qué contiene un
MKV real para poder planificar la Fase 5 en firme después.

---

## 1. Inventariar los ficheros de vídeo

El cambio de fondo: el escaneo deja de mirar solo `.srt` y pasa a inventariar
también los vídeos. Es lo que permite dibujar el árbol aunque no haya subtítulos, y
es el cimiento sobre el que la Fase 5 colgará las pistas embebidas.

**`app/models/enums.py`** — constante nueva:

```python
EXTENSIONES_VIDEO: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".mov"})
```

**`app/models/media_file.py`** (nuevo) — tabla `media_file`, hermana de
`subtitle_file`: `id`, `carpeta_id` (FK `ondelete="CASCADE"`, índice), `ruta`
(única, índice), `nombre`, `base` (el nombre sin idioma ni extensión, que es la
clave de agrupación por obra), `mtime`, `tamano_bytes`, timestamps. Migración de
Alembic revisada a mano, como la anterior.

**`app/services/scanner.py`** — `_escanear_carpeta` pasa de `rglob("*.srt")` a **un
solo recorrido** `rglob("*")` que reparte por extensión. Importa: la biblioteca está
en otro PC y recorrer la red dos veces costaría el doble. Por cada vídeo, alta o
actualización por `mtime`+`tamaño` (mismo criterio que los subtítulos, sin parsear
nada) y borrado de huérfanos en las dos tablas. `ResumenEscaneo` gana `videos`.

## 2. El árbol pasa a construirse de vídeos + subtítulos

**`app/services/library_tree.py`** — la hoja sigue siendo la **obra**, pero ahora se
alimenta de las dos tablas, agrupando por `(directorio relativo, base_sin_idioma)`.
Se reutiliza `base_sin_idioma` (`naming.py:18`), que ya funciona igual para
`Gunbuster - 01.mkv` que para `Gunbuster - 01.es.srt`.

Estado de cada obra, en un campo nuevo `estado_obra`:

| Valor | Cuándo |
|---|---|
| `DUAL` | algún subtítulo en `TRANSLATED` |
| `PENDIENTE` | hay subtítulos externos, ninguno traducido |
| `SIN_SUBTITULOS` | hay vídeo y ningún `.srt` al lado |
| `ERROR` | algún subtítulo en `ERROR` |

`NodoArbol` (`app/schemas/tree.py`) gana `estado_obra`, `tiene_video` y el agregado
`num_sin_subtitulos`; `num_obras` pasa a contar también las obras sin subtítulos.
`CarpetaOut` gana `num_videos`.

> **Límite conocido, a documentar:** vídeo y subtítulo solo se agrupan si comparten
> nombre base (`Cap 01.mkv` + `Cap 01.es.srt`). Un `.srt` con otro nombre aparecerá
> como obra aparte. Es el mismo criterio que ya usa `derivar_nombre_bilingue`.

## 3. Selector de carpetas: dejar de ocultar lo que falla

**`app/api/filesystem.py`** — sustituir `Path.iterdir()` + `is_dir()` por
`os.scandir()` con `entry.is_dir(follow_symlinks=False)`, que reconoce un *reparse
point* como directorio aunque su destino sea inalcanzable. `EntradaDirectorio` gana
`accesible: bool`, calculado con un `os.scandir` de tanteo. Al navegar a una carpeta
inaccesible, el `403` explica el motivo (hoy sale un genérico).

**`SelectorCarpeta.tsx`** — las entradas inaccesibles se pintan atenuadas, sin
permitir entrar, con la explicación: *carpeta enlazada a otro equipo, no accesible
desde aquí*. Y una nota al pie del modal sobre por qué pasa.

## 4. Estados vacíos honestos

**`App.tsx` / `ArbolSubtitulos.tsx`** — hoy el árbol vacío dice siempre «Añade una
carpeta y pulsa Escanear», aunque acabes de escanear. Tres mensajes distintos según
el caso: sin carpetas / con carpetas pero sin escanear (`ultimo_escaneo === null`) /
escaneado sin resultados, que además menciona que los subtítulos embebidos en MKV
aún no se leen.

## 5. Sondeo de los MKV reales (paso de investigación, sin código)

1. Instalar ffmpeg: `winget install Gyan.FFmpeg` — **requiere tu visto bueno**, es
   la única parte del plan que instala software.
2. `ffprobe` sobre 3 ficheros de distintas carpetas: qué pistas de subtítulo traen,
   en qué códec (`subrip`/`ass` = texto; `hdmv_pgs_subtitle`/`dvd_subtitle` =
   imagen) y en qué idiomas.
3. Informe con el resultado y recomendación para la Fase 5. **No se escribe código
   de MKV en este plan.**

## 6. Deuda: los README

- **`backend/README.md`** (vacío) — puesta en marcha con uv, estructura de `app/`,
  comandos de Alembic y de tests, y el aviso de escuchar solo en `127.0.0.1`.
- **`frontend/README.md`** (plantilla de Vite) — scripts, estructura de `src/`, y
  cómo funciona el proxy `/api`.

---

## Verificación

```powershell
cd backend
uv run alembic upgrade head
uv run pytest
uv run ruff check . ; uv run ruff format .
cd ../frontend
npm run build ; npm run lint
```

**Tests nuevos:** inventario de vídeos (alta, cambio por `mtime`, huérfanos), árbol
con vídeo sin subtítulos (`SIN_SUBTITULOS`), agrupación vídeo + `.srt` hermano en una
sola hoja, y listado del explorador con una entrada inaccesible.

**End-to-end contra la biblioteca real**, que es donde apareció el problema:

1. Añadir `Z:\Anime` y escanear → el resumen debe reportar ~215 vídeos y 0 subtítulos.
2. El árbol se despliega hasta el capítulo, con todas las hojas en
   `⚠ sin subs detectados`.
3. Dejar caer un `.srt` de prueba junto a un `.mkv`, reescanear → esa hoja pasa a
   `⏳ pendiente` sin duplicarse.
4. En el selector, `Pelis` y `Series` aparecen atenuadas y explicadas, en vez de
   desaparecer.
5. Borrar la carpeta `C:\Users\Public` que quedó de las pruebas.
