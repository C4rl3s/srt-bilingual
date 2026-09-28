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
