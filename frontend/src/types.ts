// Espejo en TypeScript de los DTOs del backend (`backend/app/schemas/`).
// Si cambia un schema de Pydantic, hay que tocar también este fichero: TypeScript
// no puede comprobar lo que devuelve la red, solo lo que nosotros le prometemos.

export type Estado = 'PENDING' | 'TRANSLATED' | 'ERROR'

/**
 * Estado de una obra (capítulo o película) de cara a la interfaz. No es lo mismo
 * que `Estado`, que describe un fichero `.srt` suelto: aquí cabe además el caso de
 * un vídeo sin ningún subtítulo externo, lo normal cuando van dentro del MKV, y
 * el de una obra con subtítulos pero sin ninguno en español o inglés que sirva de
 * origen (`SIN_ORIGEN`).
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
  idiomas: string[]
  dual: boolean
  ruta_bilingue: string | null
  /** Caracteres del subtítulo de origen: lo que costaría traducir la obra. */
  num_caracteres: number
  subtitulo_ids: number[]
  /** Origen ES/EN propuesto por la selección automática. */
  subtitulo_origen_id: number | null
  /** Coreano ya existente: si lo hay, el bilingüe sale de fusionar, sin traducir. */
  subtitulo_coreano_id: number | null
}

export interface ResumenEscaneo {
  carpetas: number
  videos: number
  nuevos: number
  actualizados: number
  sin_cambios: number
  traducidos: number
  errores: number
  huerfanos_borrados: number
  total: number
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
