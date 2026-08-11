// Único punto por el que el frontend habla con el backend.
//
// Todas las rutas cuelgan de `/api`, que el proxy de Vite reescribe hacia
// http://localhost:8000 quitando el prefijo (ver `vite.config.ts`). Nunca se
// escribe `localhost:8000` aquí: así el mismo código sirve en desarrollo y en
// producción, donde front y back se sirven del mismo origen.

import type {
  Carpeta,
  EntradaDirectorio,
  Estado,
  ListadoDirectorio,
  NodoArbol,
  ResumenEscaneo,
} from '../types'

/** Error con el código HTTP y el mensaje que manda FastAPI en `detail`. */
export class ErrorApi extends Error {
  // El campo se declara y se asigna a mano en vez de usar la propiedad de
  // parámetro (`constructor(readonly status: number)`): esa forma abreviada
  // genera código en tiempo de ejecución y el proyecto compila con
  // `erasableSyntaxOnly`, que solo admite tipos que se puedan borrar del todo.
  readonly status: number

  constructor(status: number, mensaje: string) {
    super(mensaje)
    this.status = status
    this.name = 'ErrorApi'
  }
}

async function peticion<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const respuesta = await fetch(`/api${ruta}`, {
    ...opciones,
    // El header solo hace falta cuando mandamos cuerpo; en un GET sobra.
    headers: opciones.body ? { 'Content-Type': 'application/json' } : {},
  })

  if (!respuesta.ok) {
    // FastAPI pone el motivo en `detail`; si la respuesta no es JSON, nos
    // quedamos con el código.
    const cuerpo = await respuesta.json().catch(() => null)
    throw new ErrorApi(respuesta.status, cuerpo?.detail ?? `Error HTTP ${respuesta.status}`)
  }

  // 204 No Content (el DELETE) no trae cuerpo: llamar a .json() reventaría.
  if (respuesta.status === 204) return undefined as T

  return (await respuesta.json()) as T
}

export const api = {
  listarCarpetas: () => peticion<Carpeta[]>('/folders'),

  anadirCarpeta: (ruta: string) =>
    peticion<Carpeta>('/folders', { method: 'POST', body: JSON.stringify({ ruta }) }),

  marcarCarpeta: (id: number, activa: boolean) =>
    peticion<Carpeta>(`/folders/${id}`, { method: 'PATCH', body: JSON.stringify({ activa }) }),

  borrarCarpeta: (id: number) => peticion<void>(`/folders/${id}`, { method: 'DELETE' }),

  listarRaices: () => peticion<EntradaDirectorio[]>('/fs/roots'),

  navegar: (ruta: string) =>
    peticion<ListadoDirectorio>(`/fs/browse?ruta=${encodeURIComponent(ruta)}`),

  /** Sin cuerpo el backend escanea todas las carpetas marcadas como activas. */
  escanear: () => peticion<ResumenEscaneo>('/scan', { method: 'POST' }),

  arbol: (estado?: Estado) =>
    peticion<NodoArbol[]>(`/library/tree${estado ? `?estado=${estado}` : ''}`),
}
