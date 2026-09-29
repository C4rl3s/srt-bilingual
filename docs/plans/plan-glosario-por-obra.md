# Plan — Glosario por obra (guía de traducción)

**Estado:** aprobado el 2026-09-29, con las tres propuestas de «Decisiones». En curso.

## Por qué

El repaso de S4 Pt. 1 de *Shingeki no Kyojin*, capítulos 01–06, traducidos con DeepL,
obligó a corregir **entre 139 y 195 bloques por capítulo (40–55 %)**. Casi la mitad de
los fallos eran **nombres y términos de la serie**:

- 말리 / 마를리 / 말레이 (Malasia) en vez de 마레.
- 타이탄 en vez de 거인.
- 전함 (buque de guerra) por «el acorazado».
- 화물선 (barco de carga) por «el carguero».
- 수술 (cirugía) por «operación».

Detalle de los fallos en `docs/glosarios/shingeki-no-kyojin.md`.

La **prueba del 2026-09-29** retradujo el capítulo 01 con DeepL usando glosario,
instrucciones y contexto (7.328 caracteres, lo mismo que sin ellos):

| Tipo de error | DeepL a secas | Con glosario + instrucciones + contexto |
|---|---|---|
| Términos y nombres | ~45 | **~6** |
| Registro (반말 / 존댓말) | ~50 | ~25 |
| Sentido | ~22 | ~20 (sin cambio) |
| Frases partidas | ~6 | ~3 |
| **Bloques con algo que corregir** | **139** | **~64** |

Conclusiones de la prueba:

1. **El glosario funciona**, no cuesta caracteres y es predecible.
2. **Las instrucciones** (`custom_instructions`) arreglan el registro entre niños y
   amigos, pero DeepL las cumple a medias: Magath sigue mal y aparece 수술 aunque una
   instrucción lo prohíbe. Además **juntan en una línea los diálogos con guion** (5
   bloques): comprobado aislando la opción.
3. **El contexto** (bloques vecinos, gratis) no se pudo aislar en esta prueba.
4. Los **errores de sentido no cambian**: el repaso sigue haciendo falta, pero con la
   mitad de trabajo.
5. Una entrada **genérica** del glosario hace daño: «los nueve» → 아홉 거인 convirtió
   «hace nueve años» en «아홉 거인 전부터». Las entradas deben ser frases concretas.

## Qué admite cada proveedor (comprobado)

| | DeepL | Azure |
|---|---|---|
| Glosario ES→KO | **Sí**. Se crea por API (v2/v3), se referencia con `glossary_id` y no cuesta caracteres. Límite: 1000 por cuenta | **No**. El diccionario dinámico exige que uno de los dos idiomas sea el inglés. Custom Translator admite diccionarios de frases, pero exige entrenar y desplegar un modelo en su portal; fuera de alcance |
| Instrucciones | Sí: `custom_instructions`, hasta 10 de 300 caracteres, coreano admitido. Probado con la clave del usuario | No |
| Contexto | Sí: `context`, gratis, pero se aplica a **toda la petición** | No |

## Qué se hace

### 1. La guía: un fichero por serie, en la biblioteca

Una obra es un capítulo, pero el glosario es de toda la serie. La guía es un fichero
**`srt-bilingual.toml`** en la carpeta de la serie; en el caso de prueba,
`Z:\Anime\Shingeki\srt-bilingual.toml`.

Al traducir una obra se busca subiendo desde la carpeta de la obra hasta la raíz de
su `library_folder`, y **gana el más cercano**. Así una temporada puede tener su
propia guía si hiciera falta.

¿Por qué en la biblioteca y no en la base de datos? Por el principio del proyecto: el
disco es la fuente de verdad y la BD un índice reconstruible. La guía la escribe el
usuario y no se puede reconstruir, así que va en disco. Viaja con la biblioteca y
funciona igual en el despliegue con Docker, porque está dentro del volumen montado.

TOML porque Python 3.14 lo lee sin dependencias (`tomllib`) y se edita a mano:

```toml
# Guía de traducción de srt-bilingual para esta serie.
[glosario]            # español = coreano; frases concretas, con variantes
"Marley" = "마레"
"marleyenses" = "마레인"
"titán acorazado" = "갑옷 거인"
"el acorazado" = "갑옷 거인"
"brazalete" = "완장"
"capitán Magath" = "마가트 대장"

[instrucciones]       # máx. 10, de 300 caracteres (límite de DeepL)
lista = [
  "Korean subtitles for Attack on Titan (진격의 거인)...",
  "In Latin American Spanish 'ustedes' is plural 'you', not formal: 너희, never 여러분...",
]
```

Para Shingeki se escribe la primera guía **a partir de**
`docs/glosarios/shingeki-no-kyojin.md`. El `.md` sigue siendo la referencia para el
repaso humano (registro, contexto, errores recurrentes). El `.toml` solo lleva lo
que DeepL puede usar.

### 2. `services/translation/guia.py`

- `Guia` (dataclass): `glosario: dict[str, str]`, `instrucciones: list[str]`,
  `ruta: Path`, `huella` (hash del contenido).
- `guia_de(obra, raiz) -> Guia | None`: localiza el fichero y lo lee.
- Validación al leer, con error claro en la interfaz si falla:
  - TOML mal formado.
  - Secciones o claves desconocidas (una errata como `[glossario]` no debe pasar en
    silencio).
  - Más de 10 instrucciones o de 300 caracteres.
  - Entradas vacías, que no sean texto o con tabuladores o saltos de línea (DeepL las
    rechaza).
  - Guía vacía.
- Las variantes de mayúsculas **no son duplicados**: el glosario de DeepL distingue
  mayúsculas, y «isla Paradis» e «Isla Paradis» hacen falta las dos.
- Las entradas **demasiado genéricas** («los nueve») no se detectan: no hay regla
  automática fiable. Lo explican la plantilla y el README.
- *(Cambio respecto a la primera versión del plan, que pedía rechazar duplicados sin
  distinguir mayúsculas y avisar de entradas cortas; ver motivos arriba.)*

### 3. El proveedor recibe la guía

- `Translator.traducir(textos, origen, destino, guia: Guia | None = None)`. Es un
  parámetro opcional, así que los proveedores y los falsos de los tests siguen
  cumpliendo el `Protocol`.
- Nuevo atributo `admite_guia: bool`: DeepL `True`, Azure `False`. Azure recibe la
  guía y la ignora.
- **DeepL:**
  - **Glosario cacheado por huella.** Se crea en DeepL con el nombre
    `srt-bilingual:<huella>` y se reutiliza mientras el `.toml` no cambie.
    `list_glossaries()` al primer uso; se borran los glosarios con ese prefijo que ya
    no correspondan a ninguna guía, para no acercarse al límite de 1000.
  - `custom_instructions` con la lista de la guía.
  - El glosario es **español → coreano**: con un origen en inglés no se aplica
    (no casaría con nada), y solo van las instrucciones. *(Añadido al implementar.)*
  - **Diálogos con guion**: si hay instrucciones, cada línea se traduce por separado
    y se vuelven a unir con salto de línea. Arregla la fusión de líneas comprobada en
    la prueba. Los caracteres enviados son los mismos.

### 4. El trabajo usa la guía y lo deja anotado

- `trabajos.py`: al traducir, `guia_de(obra)` se pasa al traductor.
- `translation_job` gana una columna `guia` (ruta y huella, o `NULL`), para saber
  después con qué se tradujo cada bilingüe. Migración Alembic, revisada a mano.
- **Elección de proveedor.** Si la obra tiene guía, la elección automática prefiere
  los proveedores con `admite_guia` que tengan cupo. Si ninguno tiene cupo, pasa al
  siguiente como hoy y la interfaz avisa de que se traducirá sin glosario. La regla
  vive en `services/translation/eleccion.py` y en `frontend/src/utils/cupos.ts`
  (deuda conocida): **hay que cambiar las dos**.

### 5. Interfaz

En el panel de detalle de la obra, junto al proveedor:

- «Guía: `Shingeki/srt-bilingual.toml` (57 términos, 6 instrucciones)».
- Si el proveedor elegido no la admite: «Azure no admite glosario».
- Si el fichero tiene errores, se muestran con el motivo.

No se edita la guía desde la interfaz: es un fichero de texto (ver «Fuera de alcance»).

### 6. Contexto (solo si se demuestra que mejora)

`context` se aplica a toda la petición: usarlo obliga a **una petición por bloque**,
unos 300 por capítulo y uno o dos minutos más. No cuesta caracteres.

Se mide con una prueba A/B, **guía sin contexto frente a guía con contexto**, sobre un
capítulo nuevo. Se activa (opción por guía, `contexto = true`) solo si reduce los
errores de forma clara.

## Hitos

1. **Guía**: formato, `guia.py`, localización y validación. Tests.
2. **DeepL con guía**: glosario cacheado, instrucciones, diálogos línea a línea. Azure
   declara que no la admite. Tests con cliente falso, sin llamadas reales.
3. **Trabajos y elección**: guía en el trabajo, columna `guia` con su migración,
   preferencia por proveedores con guía (backend y `cupos.ts`). Tests.
4. **Interfaz**: la guía en el panel de detalle.
5. **Guía de Shingeki** (`srt-bilingual.toml`) y **verificación e2e** con
   **S4 Pt. 1-07**, que aún no está traducido: generar, repasar y contar errores con
   los criterios del glosario. Prueba A/B del contexto (hito 6 del apartado anterior).
6. **Documentación**: bitácora, `CLAUDE.md`, README (formato de la guía) y
   `docs/modelo-datos.md` (la columna nueva).

## Riesgos y cuidados

- **No regenerar S4 Pt. 1-01 a 06**: sus bilingües están repasados a mano y
  regenerarlos los pisaría. La verificación usa el 07.
- **Glosario demasiado genérico**: se valida y se avisa (caso «los nueve»). La guía de
  Shingeki se escribe con frases, no con palabras sueltas ambiguas: `hembra`,
  `nueve`, `mandíbula` a secas.
- **Glosarios huérfanos en DeepL**: se limpian por prefijo.
- **Instrucciones cumplidas a medias**: no sustituyen al repaso; la interfaz no debe
  prometer más de lo que dan.

## Fuera de alcance

- Glosario en Azure (Custom Translator).
- Editar la guía desde la interfaz.
- Proteger los bilingües repasados a mano frente a una regeneración. Merece una mejora
  aparte: por ejemplo, detectar que el fichero cambió desde que lo escribió la app y
  pedir confirmación.
- Repaso automático del coreano.

## Decisiones (aprobadas por el usuario el 2026-09-29)

1. **Dónde vive la guía:** `srt-bilingual.toml` en la carpeta de la serie, dentro de
   la biblioteca. Se descartó una carpeta de la app (`GUIAS_DIR`) con la asociación
   por ruta mantenida a mano.
2. **Con guía se prefiere DeepL**, aunque Azure vaya primero en
   `TRANSLATION_PROVIDERS`.
3. **Contexto:** se mide en el hito 5 antes de activarlo.
