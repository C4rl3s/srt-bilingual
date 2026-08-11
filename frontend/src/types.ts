// Espejo en TypeScript de los DTOs del backend (`backend/app/schemas/`).
// Si cambia un schema de Pydantic, hay que tocar también este fichero: TypeScript
// no puede comprobar lo que devuelve la red, solo lo que nosotros le prometemos.

export type Estado = 'PENDING' | 'TRANSLATED' | 'ERROR'

/** Una carpeta vigilada, con los contadores que calcula `GET /folders`. */
export interface Carpeta {
  id: number
  ruta: string
  activa: boolean
  /** Fecha ISO en UTC, o `null` si nunca se ha escaneado. */
  ultimo_escaneo: string | null
  num_subtitulos: number
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
  idiomas: string[]
  dual: boolean
  ruta_bilingue: string | null
  num_caracteres: number
  subtitulo_ids: number[]
}

export interface ResumenEscaneo {
  carpetas: number
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
}

export interface ListadoDirectorio {
  ruta: string
  /** `null` en la raíz de una unidad: ya no se puede subir más. */
  padre: string | null
  directorios: EntradaDirectorio[]
}
