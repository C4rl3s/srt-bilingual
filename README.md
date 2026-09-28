# srt-bilingual

Aplicación web para generar subtítulos **bilingües** (español o inglés + coreano) a
partir de ficheros `.srt`, pensada para usarse junto a una biblioteca **Plex**.

En lugar de fusionar dos `.srt` independientes (que casi nunca cuadran en tiempos),
parte del `.srt` original y pone el coreano debajo de cada bloque, **reutilizando
sus marcas de tiempo**:

```
12
00:01:23,400 --> 00:01:25,900
Texto original en español
한국어 번역
```

El coreano sale de uno de dos sitios:

- **Fusión**: si la película ya tiene un `.srt` coreano, se alinea con el original
  (corrigiendo desfases y cortes distintos). No gasta cupo de traducción.
- **Traducción**: si no, lo traduce un proveedor (hoy DeepL), por lotes.

El bilingüe se escribe junto al vídeo como `<vídeo>.ES-KO.bilingue.srt`, y Plex lo
muestra como «Español (KO)».

## Stack

- **Backend:** Python 3.14 + FastAPI, gestionado con [uv](https://docs.astral.sh/uv/). Base de datos SQLite.
- **Frontend:** React + TypeScript + Vite.
- **Traducción:** capa multi-proveedor; DeepL como primera implementación.

## Estructura

```
srt-bilingual/
├── backend/    # API FastAPI (uv): ver backend/README.md
├── frontend/   # SPA React + Vite: ver frontend/README.md
└── docs/       # modelo de datos, planes y bitácoras de cada fase
```

## Puesta en marcha (desarrollo)

Hacen falta [uv](https://docs.astral.sh/uv/) y Node.js 24.

### 1. Backend

```bash
cd backend
uv sync                                   # instala dependencias en .venv
cp .env.example .env                      # y rellena la clave de DeepL (ver abajo)
uv run alembic upgrade head               # crea o actualiza la base de datos SQLite
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 · documentación OpenAPI: http://localhost:8000/docs

Variables del `.env` (todas opcionales salvo la clave, si se va a traducir):

| Variable | Para qué | Por defecto |
|---|---|---|
| `DEEPL_API_KEY` | Clave de la API de DeepL. Sin ella solo funciona la fusión | — |
| `TRANSLATION_PROVIDER` | Proveedor de traducción activo | `deepl` |
| `DATABASE_URL` | Base de datos | `sqlite:///./srt_bilingual.db` |
| `OUTPUT_DIR` | Carpeta alternativa para los bilingües (si la biblioteca es de solo lectura) | vacía: junto al vídeo |

> **Escucha solo en local.** `/fs/browse` lista directorios de la máquina para que
> el selector de carpetas funcione. Deja uvicorn en `127.0.0.1`, el valor por
> defecto.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Vite reenvía las peticiones a `/api/*` al backend del puerto 8000.

### 3. Primer uso

1. En la interfaz: **Biblioteca › Gestionar carpetas**, añade las carpetas de tu
   biblioteca y pulsa **Escanear**.
2. Elige una película: el panel de la derecha dice qué subtítulo usará de origen,
   si ya hay coreano (fusión) y cómo quedará.
3. **Generar bilingüe**. El progreso aparece en **Trabajos**.

## Despliegue

**Aún no implementado.** El destino previsto es un servidor local que hará de NAS,
con Docker, donde también correrá Plex. Las carpetas de la biblioteca serán locales
(montadas como volúmenes), sin recursos compartidos de red. Cuando llegue ese paso,
esta sección explicará la imagen, el `docker compose`, los volúmenes y las
variables. Los requisitos están en `CLAUDE.md` (Estado del plan).

## Tests

```bash
cd backend && uv run pytest               # 196 tests; ninguno llama a DeepL
cd frontend && npm run build              # comprueba los tipos y compila
```

## Estado del proyecto

- [x] **Fase 0** — Esqueleto del proyecto y conexión front↔back.
- [x] **Fase 1** — Modelos SQLite, escáner de carpetas, parser SRT y conteo de caracteres.
- [x] **Fase 2** — Gestión de carpetas desde la interfaz e inventario de vídeo.
- [x] **Fase 3** — Traducción (DeepL), fusión con coreano existente, generación del
  bilingüe, selección del subtítulo de origen, renombrado para Plex e interfaz nueva.
- [ ] **Fase 4** — Cuotas por proveedor y elección de proveedor según el cupo libre.
- [ ] **Fase 5** — Soporte MKV: bilingües a partir de las pistas embebidas.
- [ ] **Despliegue** con Docker en el servidor local, y web de documentación.
