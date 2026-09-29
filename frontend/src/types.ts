// Espejo en TypeScript de los DTOs del backend (`backend/app/schemas/`).
// Si cambia un schema de Pydantic, hay que tocar también este fichero: TypeScript
// no puede comprobar lo que devuelve la red, solo lo que nosotros le prometemos.

export type Estado = 'PENDING' | 'TRANSLATED' | 'ERROR'

export type Idioma = 'ES' | 'EN' | 'KO' | 'FR' | 'DE' | 'IT' | 'PT' | 'JA' | 'ZH' | 'UNKNOWN'

/**
 * Estado de una obra (capítulo o película) de cara a la interfaz. No es lo mismo
 * que `Estado`, que describe un subtítulo suelto: aquí cabe además el caso de un
 * vídeo sin ningún subtítulo (ni `.srt` al lado ni pistas de texto dentro, o aún no
 * se han leído sus pistas), y el de una obra con subtítulos pero sin ninguno en
 * español o inglés que sirva de origen (`SIN_ORIGEN`).
 */
export type EstadoObra = 'DUAL' | 'PENDIENTE' | 'SIN_ORIGEN' | 'SIN_SUBTITULOS' | 'ERROR'

/** Una carpeta vigilada, con los contadores que calcula `GET /folders`. */
export interface Carpeta {
  id: number
  ruta: string
  activa: boolean
  /** Fecha ISO en UTC, o `null` si nunca se ha escaneado. */
  ultimo_escaneo: string | null
  num_subtitulos: number
  num_videos: number
  num_dual: number
  num_pendientes: number
  num_errores: number
}

/**
 * Nodo del árbol de la biblioteca. Es recursivo: `hijos` vuelve a ser lo mismo.
 * Con `hoja: true` es una obra (capítulo o película) y valen los campos de abajo;
 * con `hoja: false` es una carpeta y valen los contadores agregados.
 */
export interface NodoArbol {
  nombre: string
  ruta: string
  hoja: boolean
  hijos: NodoArbol[]
  num_obras: number
  num_dual: number
  num_errores: number
  num_sin_subtitulos: number
  num_sin_origen: number
  /** Solo en las hojas; `null` en las carpetas. */
  estado_obra: EstadoObra | null
  tiene_video: boolean
  idiomas: Idioma[]
  dual: boolean
  ruta_bilingue: string | null
  /** Lo que costaría traducir la obra: lo mismo que reservaría el trabajo. */
  num_caracteres: number
  /** `false` si el origen es una pista sin extraer: `num_caracteres` es una estimación. */
  caracteres_exactos: boolean
  /** El origen propuesto es una pista dentro del vídeo, no un `.srt`. */
  origen_en_video: boolean
  subtitulo_ids: number[]
  /** Origen ES/EN propuesto por la selección automática. */
  subtitulo_origen_id: number | null
  idioma_origen: Idioma | null
  /** Coreano ya existente: si lo hay, el bilingüe sale de fusionar, sin traducir. */
  subtitulo_coreano_id: number | null
  /** Guía de traducción de la serie (`srt-bilingual.toml`) según el último escaneo.
   *  Con ella se prefiere un proveedor que la admita (ver `utils/cupos.ts`). */
  ruta_guia: string | null
}

export interface ResumenEscaneo {
  carpetas: number
  videos: number
  /** Guías de traducción vistas. */
  guias: number
  nuevos: number
  actualizados: number
  sin_cambios: number
  traducidos: number
  errores: number
  huerfanos_borrados: number
  total: number
}

/**
 * Progreso de la lectura de pistas que sigue a cada escaneo (`GET /scan/sondeo`):
 * `ffprobe` abre la cabecera de cada vídeo nuevo o cambiado, en segundo plano.
 */
export interface ProgresoSondeo {
  en_curso: boolean
  hechos: number
  total: number
  /** Vídeos que no se pudieron leer: se reintentan en el próximo escaneo. */
  errores: number
  ultimo_error: string | null
}

export interface EntradaDirectorio {
  nombre: string
  ruta: string
  /** `false` si existe pero no se puede abrir desde este equipo. */
  accesible: boolean
  motivo: string | null
}

export interface ListadoDirectorio {
  ruta: string
  /** `null` en la raíz de una unidad: ya no se puede subir más. */
  padre: string | null
  directorios: EntradaDirectorio[]
}

// --- Generación de bilingües (Fase 3) ------------------------------------------------

export type ModoTrabajo = 'TRADUCCION' | 'FUSION'
export type EstadoTrabajo = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED'

export interface Trabajo {
  id: number
  modo: ModoTrabajo
  estado: EstadoTrabajo
  /** En qué está mientras corre: `EXTRAYENDO` las pistas del vídeo (sin progreso de
   *  bloques, 1–1,5 min por episodio por la red) o `GENERANDO`. Nula fuera de `RUNNING`. */
  fase: 'EXTRAYENDO' | 'GENERANDO' | null
  /** Aún no ha terminado: mientras haya alguno, el frontend sigue preguntando. */
  activo: boolean
  subtitulo_id: number | null
  subtitulo_coreano_id: number | null
  ruta_origen: string
  ruta_bilingue: string | null
  idioma_origen: Idioma
  proveedor: string | null
  /** La guía de la serie con que se tradujo, si el proveedor la usó. */
  guia: string | null
  num_caracteres: number
  caracteres_previstos: number
  calidad_alineacion: number | null
  bloques_totales: number
  bloques_procesados: number
  mensaje_error: string | null
  creado_en: string
  iniciado_en: string | null
  finalizado_en: string | null
}

export interface RespuestaTraduccion {
  trabajos: Trabajo[]
  rechazados: { subtitulo_id: number; motivo: string }[]
}

export type MotivoDescarte = 'ERROR' | 'IMAGEN' | 'IDIOMA' | 'FORZADO' | 'POCOS_BLOQUES'

export type FormatoSubtitulo = 'SRT' | 'ASS' | 'VTT' | 'MOV_TEXT' | 'PGS' | 'VOBSUB'

export interface Candidato {
  subtitulo_id: number
  nombre: string
  ruta: string
  idioma: Idioma
  num_bloques: number
  es_forzado: boolean
  es_sdh: boolean
  descarte: MotivoDescarte | null
  formato: FormatoSubtitulo
  /** Pista incrustada en el vídeo (Fase 5) en vez de un `.srt` propio. */
  es_pista: boolean
  indice_pista: number | null
  titulo_pista: string | null
  /** `false` si `num_bloques` sale de la cabecera de la pista (o es 0 = no se sabe). */
  metricas_exactas: boolean
}

export interface Muestra {
  tiempo: string
  origen: string
  /** `null` si el coreano saldrá de traducir: traducir la muestra gastaría cupo. */
  coreano: string | null
}

export interface Candidatos {
  obra: string
  muestra: Muestra[]
  origen_id: number | null
  coreano_id: number | null
  calidad_alineacion: number | null
  fusion_aceptable: boolean | null
  candidatos: Candidato[]
  /** El origen o el coreano son pistas sin extraer: sin muestra ni calidad hasta
   *  `POST /videos/{video_id}/extraer`. */
  extraccion_pendiente: boolean
  video_id: number | null
  extrayendo: boolean
  error_extraccion: string | null
}

/** Respuesta de `POST /videos/{id}/extraer`. */
export interface Extraccion {
  video_id: number
  en_curso: boolean
  error: string | null
}

/** El cupo de un proveedor configurado (`GET /translate/cupos`). */
export interface EstadoCupo {
  proveedor: string
  /** `false` si no se puede usar ahora (sin clave, desconocido…); ver `motivo`. */
  disponible: boolean
  motivo: string | null
  /** API: lo dice el proveedor · REGISTRO: suma de lo enviado por la app este mes. */
  fuente: 'API' | 'REGISTRO'
  usados: number
  /** Lo que aún no han enviado los trabajos en cola o en curso. */
  reservados: number
  limite: number | null
  libre: number | null
  /** Si aprovecha la guía de la serie (glosario e instrucciones). Hoy solo DeepL. */
  admite_guia: boolean
}

export interface PropuestaRenombrado {
  subtitulo_id: number
  ruta_actual: string
  ruta_nueva: string
  conflicto: 'EXISTE' | 'DUPLICADO' | 'ERROR_DISCO' | null
}

export interface ResultadoRenombrado {
  renombrados: PropuestaRenombrado[]
  rechazados: PropuestaRenombrado[]
}
