# CLAUDE.md — srt-bilingual

Guía de contexto para Claude Code. Léela al empezar cualquier sesión en este repo.

## Qué es y por qué existe

App web personal (uso doméstico, un solo usuario) para generar subtítulos
**bilingües** a partir de ficheros `.srt`, pensada para usarse junto a una
biblioteca **Plex**. Caso de uso real: ver películas/series con doble subtítulo
(p. ej. español/inglés + **coreano**), algo que ni las plataformas ni Plex
permiten de forma nativa.

**Idea central (resuelve el problema de alineación temporal):** en vez de fusionar
dos `.srt` independientes —que casi nunca cuadran en tiempos— se parte del `.srt`
original y se traduce **bloque a bloque reutilizando las marcas de tiempo
originales**. El resultado por bloque:

```
12
00:01:23,400 --> 00:01:25,900
Texto original en español
한국어 번역
```

## Stack

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | **Python + FastAPI** | Gestionado con **uv** (no pip/venv manual). Python **3.14**. |
| Base de datos | **SQLite** | Un solo usuario, sin servidor; fichero local. |
| Frontend | **React + TypeScript + Vite** | El usuario aprende React aquí; mantener el código claro y didáctico. |
| Traducción | Capa **multi-proveedor** | Azure Translator (REST con httpx) y DeepL (SDK oficial), con elección automática según cupo libre. |
| Vídeos | ffmpeg (binario externo) | `ffprobe` lee las pistas de subtítulo; `ffmpeg` las extrae. Sin librería Python: dos llamadas a `subprocess`. |

Decisiones tomadas (no re-litigar sin motivo):
- Python+FastAPI sobre Java/Spring: ecosistema de subtítulos/MKV superior, más
  ligero para uso doméstico, y el usuario quiere aprender Python.
- SQLite sobre MySQL: un solo usuario, cero mantenimiento.
- Traducción con abstracción multi-proveedor desde el día 1 (el upgrade de contar
  caracteres por API y elegir proveedor al vuelo encaja sin reescribir).

## Arquitectura (monorepo dividido)

```
srt-bilingual/
├── CLAUDE.md          # este fichero
├── README.md          # docs de usuario / puesta en marcha
├── .gitignore
├── backend/           # API FastAPI (uv) — Python 3.14
│   ├── app/
│   │   ├── main.py            # arranque FastAPI + CORS + /health + routers
│   │   ├── config.py          # settings vía .env (pydantic-settings)
│   │   ├── db.py              # engine + sesión SQLAlchemy + get_db
│   │   ├── models/            # tablas ORM: enums, library_folder, subtitle_file,
│   │   │                      #   media_file
│   │   ├── schemas/           # Pydantic (DTOs request/response): scan, subtitle,
│   │   │                      #   folder, tree
│   │   ├── api/               # routers: subtitles, scan, folders, filesystem,
│   │   │                      #   library, translate, renombrado, videos
│   │   └── services/
│   │       ├── scanner.py     # escaneo y reconciliación disco ↔ BD
│   │       ├── library_tree.py # árbol derivado de las rutas de subtitle_file
│   │       ├── obras.py       # agrupación en obras + dónde va su bilingüe
│   │       ├── subtitles/     # modelo (Bloque), naming, srt_parser, ass_parser,
│   │       │                  #   lectura (srt o pista extraída), seleccion,
│   │       │                  #   renombrado (Plex), alineacion (modo fusión)
│   │       ├── bilingual.py   # genera el .srt bilingüe (escritura atómica)
│   │       ├── trabajos.py    # crear/ejecutar trabajos (BackgroundTasks)
│   │       ├── mkv/           # pistas incrustadas: sondeo (ffprobe, en segundo
│   │       │                  #   plano tras el escaneo) y extracción a la caché
│   │       │                  #   (ffmpeg, una pasada por vídeo) (Fase 5)
│   │       └── translation/
│   │           ├── base.py    # interfaz Translator (Protocol) + excepciones
│   │           ├── deepl_provider.py  # informa de su cupo (ConCupo)
│   │           ├── azure_provider.py  # no informa: cupo por registro de la app
│   │           ├── registry.py        # nombre → proveedor; límites configurados
│   │           ├── consumo.py         # cupo de cada proveedor (API o registro)
│   │           └── eleccion.py        # proveedor según cupo libre
│   ├── alembic/               # migraciones (env.py toma la URL de settings)
│   ├── alembic.ini
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml         # deps + config de pytest y ruff
└── frontend/          # SPA React + Vite
    ├── src/
    │   ├── App.tsx            # esqueleto: cabecera + sección activa + datos comunes
    │   ├── types.ts           # espejo TS de los DTOs del backend
    │   ├── api/client.ts      # envoltorio de fetch sobre /api/...
    │   ├── hooks/             # useTrabajos y useSondeo (polling), usePersistente
    │   │                      #   (localStorage)
    │   ├── utils/             # formato (números, títulos), biblioteca (árbol, filtros)
    │   └── components/        # Cabecera, Trabajos, Renombrado, Carpetas, Iconos y
    │                          #   biblioteca/ (árbol, contenido, paneles de detalle
    │                          #   y selección). Diseño: docs/plans/plan-fase3.md §10
    └── vite.config.ts         # proxy /api -> http://localhost:8000
```

> Nota: las carpetas marcadas `(Fase N)` aún no existen; se crean al llegar a esa
> fase. No las crees vacías por adelantado.

## Modelo de datos

Esquema detallado (tablas, columnas, índices y diagrama): **`docs/modelo-datos.md`**
(fuente de verdad) y su versión visual autocontenida `docs/modelo-datos.html`.
Resumen:

- `library_folder` — carpetas a vigilar (las mismas compartidas en Plex). *(Fase 1)*
- `media_file` — contenedores de vídeo inventariados (no se abren; sostienen el
  árbol cuando no hay `.srt` al lado). *(Fase 2 bis)*
- `subtitle_file` — ruta, idioma origen, nº caracteres (sin marcas de tiempo),
  nº bloques, estado (`PENDING`/`TRANSLATED`/`ERROR`), ruta del bilingüe generado,
  idioma destino, proveedor usado, `mtime`+tamaño (para no reparsear lo no cambiado),
  timestamps. *(Fase 1)*
- `translation_job` — cada generación de bilingüe (traducción o fusión), su progreso
  y los caracteres enviados al proveedor. FKs a `subtitle_file` con `SET NULL` y
  rutas copiadas: es historial y sobrevive a sus subtítulos. Es también el
  **registro de consumo** de la Fase 4 (con `caracteres_previstos` para reservar
  cupo). *(Fase 3)*
- ~~`provider_usage`~~ — descartada en la Fase 4: duplicaría lo que ya suma
  `translation_job` (ver `docs/plans/plan-fase4.md`).

**Principio rector:** el sistema de ficheros es la fuente de verdad; la base de datos
es un índice reconstruible. Un escaneo siempre puede rehacerse desde cero. **Única
excepción:** `translation_job`, que es historial de trabajos y de cuota consumida.

## Convenciones

**General**
- Idioma del código y comentarios: **español** (nombres de dominio, docstrings,
  mensajes). Mantener la densidad de comentarios del código circundante.
- Estados/enums en mayúsculas: `PENDING`, `TRANSLATED`, `ERROR`.

**Backend (Python)**
- `snake_case` para funciones/variables/módulos; `PascalCase` para clases.
- Módulos y carpetas en `snake_case` y singular cuando es un servicio
  (`scanner.py`), plural para colecciones de tipos (`models/`, `schemas/`).
- Linter/formatter: **ruff** (`line-length = 100`, `target-version = py314`).
- Tests con **pytest** en `backend/tests/`, fichero `test_*.py`. `pythonpath = ["."]`
  ya configurado, así que los imports son `from app.main import app`.
- Type hints siempre que aporten claridad.

**Frontend (React/TS)**
- Componentes en `PascalCase`; hooks `useX`; ficheros de componente `PascalCase.tsx`.
- Las llamadas al backend van **siempre a `/api/...`** (el proxy de Vite reescribe
  `/api` → backend en `:8000`, quitando el prefijo). No hardcodear `localhost:8000`.

**Git**
- Rama principal: `main`. Commits estilo convencional (`feat:`, `chore:`, `fix:`…).
- No commitear sin que el usuario lo pida.

## Comandos habituales

```powershell
# Backend
cd backend
uv sync                                          # instalar deps
uv run alembic upgrade head                      # aplicar migraciones (crea/actualiza la BD)
uv run uvicorn app.main:app --reload --port 8000 # API en :8000  (/docs para OpenAPI)
uv run pytest                                    # tests
uv run ruff check .                              # lint
uv run ruff format .                             # formateo
uv add <paquete>                                 # añadir dependencia de runtime
uv add --dev <paquete>                           # añadir dependencia de desarrollo

# Migraciones (tras tocar un modelo de app/models/)
uv run alembic revision --autogenerate -m "descripcion"  # generar; REVISAR siempre lo generado
uv run alembic upgrade head                              # aplicar
uv run alembic current                                   # revisión aplicada
uv run alembic downgrade -1                              # deshacer la última

# Frontend
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check (tsc) + build de producción
```

## Entorno (importante)

- **SO:** Windows 11, shell **PowerShell** (la herramienta Bash POSIX no está
  disponible en este entorno).
- `uv` y `Node` se instalaron con **winget** (`astral-sh.uv`, `OpenJS.NodeJS.LTS`).
  Si una sesión no los encuentra en el PATH, recargar con:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`
- Versiones de referencia: uv 0.11.x, Node 24.x, Python 3.14.6, git 2.54.

## Aprendizaje (cierre de cada fase)

Este proyecto es también el vehículo con el que el usuario aprende Python y React.
Al **terminar cada fase** (código escrito, ejecutado y verificado) hay un repaso
docente con comandos globales propios:

| Comando | Cuándo | Qué hace |
|---|---|---|
| `/teachpy` | Fases con backend (1, 3, 4, 5) | Recorre **todo** el Python escrito en la fase y lo explica a nivel de lenguaje |
| `/teachreact` | Fases con frontend (2, 4) | Ídem con el código React/TS |

Definidos en `C:\Users\Beicon\.claude\commands\teachpy.md` y `teachreact.md`.

Cómo se comportan (importante, para no desvirtuarlos):

- **Por defecto son solo explicación**: índice de ficheros, recorrido de arriba
  abajo citando `fichero:línea`, centrado en lo **idiomático del lenguaje** y en el
  **por qué** de cada decisión. Nada de conceptos universales de programación —el
  usuario ya es desarrollador backend.
- **No proponen ejercicios ni examinan de entrada.** Ese es un modo aparte que
  activa el usuario ("ponme ejercicios", "examíname").
- En modo ejercicios se pregunta **siempre** antes: ¿practicar sobre el código real
  del proyecto (solo cambios que le convengan al proyecto) o con ejercicios
  originales aparte, fuera del código de producción? El proyecto tiene un propósito
  y no se deforma para practicar.
- En modo docente **no se modifica código** salvo petición explícita.

Al cerrar una fase, ofrecer el repaso; no darlo por hecho ni lanzarlo sin pedirlo.

## Estado del plan

Plan de desarrollo aprobado en 6 fases.

- [x] **Fase 0 — Esqueleto + conexión front↔back.** Estructura del monorepo,
  backend con `/health` + CORS + test, frontend Vite consumiendo `/api/health`
  vía proxy. Verificado end-to-end. Commit `225ff60`.
- [x] **Fase 1 — Núcleo backend.** Config (.env), modelos SQLite + Alembic, scanner
  de carpetas, parser SRT + conteo de caracteres (limpiando índices y marcas de
  tiempo), detección de estado. Endpoints: `GET /subtitles`, `POST /scan`,
  `GET /subtitles/{id}`. 48 tests en verde y verificación e2e hecha
  (2026-07-30). Bitácora: `docs/bitacora-fase1.md`. Commit `4ebbc0f`.
- [x] **Fase 2 — Gestión de carpetas + vista de estado.** Alta y baja de carpetas
  desde la interfaz (explorador de disco servido por el backend), casilla por
  carpeta para elegir cuáles entran en el escaneo (columna `activa`, persistida) y
  botón de "Escanear". El resultado se muestra como un **árbol derivado de las
  rutas** que llega hasta la obra (capítulo/película), con los idiomas disponibles
  y si ya existe su versión dual. `MEDIA_FOLDERS` desaparece: `library_folder` pasa
  a ser la única autoridad sobre qué se vigila. 79 tests en verde y verificación
  e2e hecha (2026-08-11). Plan: `docs/plans/plan-fase2.md`. Bitácora:
  `docs/bitacora-fase2.md`. Commit `54d8839`.
- [x] **Fase 2 bis — Inventario de vídeo y arreglos.** El escaneo inventaría también
  los ficheros de vídeo (tabla `media_file`), en un solo recorrido del disco, y el
  árbol se alimenta de vídeos + subtítulos, con un `estado_obra` por hoja
  (`DUAL`/`PENDIENTE`/`SIN_SUBTITULOS`/`ERROR`). Así la biblioteca real —toda `.mkv`,
  sin un solo `.srt`— se puede dibujar. El selector deja de ocultar en silencio las
  carpetas que no puede abrir y los estados vacíos distinguen sin carpetas / sin
  escanear / escaneado sin resultados. READMEs de backend y frontend escritos.
  88 tests en verde y verificación e2e hecha (2026-08-11). Plan:
  `docs/plans/plan-inventario-video-y-arreglos.md`. Bitácora:
  `docs/bitacora-inventario-video-y-arreglos.md`. Commit `95c954c`.
- [x] **Fase 3 — Traducción + generación bilingüe.** Solo `ES-KO` / `EN-KO`: sin
  origen ES/EN la obra no es elegible (`SIN_ORIGEN`). Detección de idioma por
  nombre y contenido, **selección del subtítulo de origen** (heurística + override
  manual), **modo fusión** (si ya hay coreano se alinea con el origen, sin gastar
  cupo), `Translator` multi-proveedor con DeepL, `bilingual.py` reutilizando los
  tiempos, trabajos en `BackgroundTasks` con progreso, **renombrado para Plex** e
  **interfaz nueva** diseñada con el usuario (lienzo de diseño) y verificada en el
  navegador. 196 tests en verde (2026-09-28). Plan: `docs/plans/plan-fase3.md`.
  Bitácora: `docs/bitacora-fase3.md`. Repaso docente aplazado por el usuario.
- [x] **Fase 4 — Cupos por proveedor y elección automática.** **Azure Translator**
  (plan gratuito F0) como segundo proveedor junto a DeepL. Cupo de cada proveedor:
  lo que dice su API (DeepL) o el **registro de la app** del mes (Azure, que no
  tiene API de consumo), más lo reservado por trabajos en cola. Cada traducción va
  al primero de `TRANSLATION_PROVIDERS` con cupo libre; sin cupo, no se crea el
  trabajo. Interfaz con el cupo de cada proveedor y de dónde sale la cifra. Tabla
  `provider_usage` descartada (el consumo sale de `translation_job`). 227 tests en
  verde y verificado con las cuentas reales (2026-09-28). Plan:
  `docs/plans/plan-fase4.md`. Bitácora: `docs/bitacora-fase4.md`.
- [x] **Fase 5 — Subtítulos dentro de los vídeos** (2026-09-28). Incluye la prueba
  de calidad que pidió el usuario (*Moonrise* 01: fusión con la pista coreana de
  Netflix frente a Azure y DeepL). Orden de calidad: fusión ≫ DeepL (~10 % de
  líneas mal) > Azure (~15 %, ~20 % antes de la mejora). La mejora ya aplicada:
  las líneas de un bloque se traducen unidas y el coreano vuelve en dos líneas
  (`subtitles/lineas.py`), salvo los diálogos con guion. Decisión del usuario tras
  la prueba: **elegir proveedor por obra** en el detalle (automático por defecto;
  el elegido pasa la misma comprobación de clave y cupo). Lo hecho:
  - Una pista incrustada es una fila de `subtitle_file` con `video_id`: la
    selección, los trabajos y la interfaz la tratan como un `.srt` más, y una obra
    puede mezclar pista y `.srt` (p. ej. pista española + `.srt` coreano).
  - Tras cada escaneo, `ffprobe` lee en segundo plano la cabecera de los vídeos
    nuevos o cambiados (`services/mkv/sondeo.py`). Extraer obliga a leer el MKV
    entero (1–1,5 min por episodio por la red), así que va dentro del trabajo o
    del botón «Extraer pistas», con caché (`CACHE_DIR`).
  - Parser ASS propio que deja solo el diálogo (fuera carteles, dibujos, karaoke y
    opening/ending). Las líneas de la cabecera no se comparan entre pistas: en los
    fansubs las inflan los carteles.
  - Tras extraer, el trabajo revisa lo elegido con el texto real (forzado, otro
    idioma) y ajusta la reserva de cupo a la cifra exacta.
  - **No se inyecta nada en el MKV**: el bilingüe es siempre un `.srt` junto al
    vídeo. **Sin OCR**: 130 capítulos de Series solo tienen origen en imagen (PGS).
    **Castellano antes que latino.** (Decisiones del usuario.)
  - Paneles laterales de la biblioteca redimensionables arrastrando su borde.
  - 298 tests; verificado con Anime real (207 obras elegibles, 27 fusionables;
    *Moonrise* 01–03 fusionados y *Shingeki* 01 traducido, en el NAS). Plan:
    `docs/plans/plan-fase5.md`. Bitácora: `docs/bitacora-fase5.md`.
- [ ] **Al terminar — despliegue con Docker en un servidor local** (requisito del
  usuario, 2026-09-28). **El equipo aún no existe**: lo que se entrega es
  **documentación e instrucciones** para cuando se monte, no un despliegue
  ejecutado. La app acabará en un equipo propio que hará de **NAS**,
  con el sistema operativo aún por decidir, que despliega apps con **Docker** y
  donde correrá también **Plex**. Consecuencias para el diseño de lo que quede:
  - **No habrá SMB**: las carpetas de la biblioteca serán locales al equipo,
    montadas como volúmenes en el contenedor (p. ej. `/media/Pelis`). Nada debe
    depender de Windows, de `Z:` ni de rutas UNC. Las rutas de `library_folder`
    cambiarán; como la BD es un índice reconstruible, basta volver a añadir las
    carpetas y escanear. `translation_job` guarda rutas antiguas, pero solo como
    historial.
  - Configuración por variables de entorno (ya es así con `.env`), la base
    SQLite en un volumen persistente y el frontend compilado servido desde el
    propio contenedor o un proxy.
  - El explorador `/fs/browse` debe limitarse a los volúmenes montados, y el
    servicio escuchar solo en la red local.
  - Hay que documentar, **como mínimo en un README**, cómo levantar la app en
    desarrollo y cómo desplegarla (imagen, `docker compose`, volúmenes,
    variables).
- [ ] **Al terminar — web de documentación.** Una sola web con secciones que
  reutilice todo lo escrito por el camino (bitácoras, decisiones, fases, modelo de
  datos). Esta sí va **en local y publicada en remoto**.

**Documentación:** vive en `docs/`, dentro del repo, y se versiona en el mismo
commit que el código que describe. Los HTML, autocontenidos (sin CDN) para abrirlos
con doble clic; los diagramas, Mermaid en markdown. Nada se publica fuera de la
máquina sin pedírselo antes al usuario.

Cada fase deja dos documentos: el **plan** en `docs/plans/plan-faseN.md` (qué se va
a hacer, escrito antes de empezar) y la **bitácora** en `docs/bitacora-faseN.md`
(qué acabó pasando, con decisiones y verificación). Un cambio de scope se refleja
dentro del plan de esa fase, no en un fichero nuevo.

## Notas / deuda técnica

**Hallazgos sobre la biblioteca real, que condicionan el plan:**

- El recurso es `\\192.168.1.130\Compartido`, montado en `Z:`, con tres carpetas:
  `Anime`, `Pelis` y `Series`. Las tres son *junctions* al disco del otro equipo.
- **2026-09-27: concedido el acceso a las tres y resueltos los dos bloqueantes.** Antes
  solo se abría `Anime` (`Pelis` y `Series` daban error al recorrerlas) y el recurso
  era de **solo lectura**. Hoy las tres se listan y **se puede escribir en todas**
  (verificado creando y borrando un fichero de prueba en cada una), así que la
  convención de dejar el `.bilingue.srt` junto al original es viable.
- Inventario: **Anime** 215 `.mkv` / 0 `.srt`; **Series** 184 `.mkv` / 0 `.srt`;
  **Pelis** 29 `.mkv` + 196 `.mp4`/`.avi` y **686 `.srt`** en 176 carpetas de película.
- **Por eso la Fase 5 deja de necesitar adelantarse.** Pelis da banco de pruebas real
  a la Fase 3 y se recupera el orden original del plan. Detalle en
  `docs/plans/plan-fase3.md`.
- **Sondeo con `ffprobe` sobre los 215 MKV de Anime (2026-09-08): las 2388 pistas de
  subtítulo son texto** (1736 `ass` + 652 `subrip`), **cero PGS/VobSub**. No hace
  falta OCR, así que la Fase 5 se abarata mucho. Además, **27 ficheros ya traen pista
  coreana** (Netflix): para esos el bilingüe sale sin gastar cuota de traducción.
  Detalle en `docs/bitacora-inventario-video-y-arreglos.md`.
- **Los `.srt` reales de Pelis no son uniformes** y condicionan la Fase 3: 461 de 686
  viven en una subcarpeta `Subs\` con nombres que no citan la obra (`English.srt`),
  52 obras no declaran idioma en ningún nombre, hay forzados que no se anuncian como
  tales y **548 de 686 empiezan con un bloque de publicidad** que hoy se está
  contando en `num_caracteres`. Los cinco hallazgos, con cifras, en
  `docs/plans/plan-fase3.md`.

**Deuda técnica:**

- uv eligió **Python 3.14**. Si alguna librería futura (p. ej. MKV) no tuviera
  wheel para 3.14, fijar 3.12 con `uv python pin 3.12`.
- Warning de deprecación de `TestClient`/httpx (sugiere `httpx2`). Inofensivo;
  abordar cuando moleste.
- Idioma destino por defecto coreano (`KO`), configurable con `DEFAULT_TARGET_LANG`.
- **El cupo de Azure sale del registro de la app**: no ve lo gastado con esa clave
  fuera de ella, y toma el mes natural aunque Azure pueda reiniciar el cupo en otra
  fecha. Se avisa en la interfaz.
- `frontend/src/utils/cupos.ts` (`repartir`) **reproduce la regla** de
  `services/translation/eleccion.py` para prever el proveedor antes de generar. Si
  se cambia la regla, hay que cambiar las dos.
- **Nunca reescribir ficheros con `Get-Content | Set-Content`** en PowerShell 5.1:
  corrompe el UTF-8 (pasó en la Fase 3; detalle en `docs/bitacora-fase4.md`).
- Los tests crean el esquema con `Base.metadata.create_all()`, no con Alembic (más
  rápido). No detectan por sí solos que una migración se haya quedado desfasada
  respecto a los modelos; tras tocar un modelo, generar la migración y revisarla.
- `alembic.ini` conserva la línea `sqlalchemy.url` de la plantilla, pero es inerte:
  `alembic/env.py` la sobrescribe con `settings.database_url`.
- `GET /library/tree` reconstruye el árbol entero en memoria en cada petición. Para
  una biblioteca doméstica sobra; si algún día pesa, el sitio donde paginar o cachear
  es `services/library_tree.py`.
- **Estado en memoria del proceso**: el progreso del sondeo de pistas y el estado de
  las extracciones pedidas desde la interfaz (`services/mkv/`) viven en el proceso
  del backend, igual que el cerrojo por vídeo. Con un solo usuario y un solo proceso
  de uvicorn basta; con varios *workers* no se verían entre sí.
- `ResumenEscaneo.total` cuenta solo los `.srt`: las pistas de los vídeos se leen
  después, en segundo plano, y no entran en el resumen del escaneo.
- **OCR de pistas de imagen** (PGS/VobSub) fuera de la Fase 5 por decisión del
  usuario: 130 capítulos de Series (*Better Call Saul*) solo tienen ES/EN así. Sería
  una fase aparte.
- El explorador `/fs/browse` deja navegar todo el disco a propósito (lo necesita el
  selector). Por eso el servidor debe escuchar solo en `127.0.0.1`.
