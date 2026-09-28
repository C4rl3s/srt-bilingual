// Cómo se recorre el árbol que devuelve `GET /library/tree` para pintar la
// biblioteca: qué carpetas salen en el árbol de navegación y qué obras se ven al
// elegir una.

import type { NodoArbol } from '../types'
import { tituloLegible } from './formato'

/**
 * Una obra lista para pintar: su hoja del árbol más un título legible.
 *
 * El título sale de la carpeta de la película cuando la hoja vive en una
 * (`Mercy (2026) [1080p]…` es más legible que `Mercy.2026.1080p.WEBRip…`), y del
 * propio nombre en los episodios.
 */
export interface Obra {
  nodo: NodoArbol
  titulo: string
  anio: string | null
}

/**
 * ¿Sale esta carpeta en el árbol de navegación?
 *
 * Solo las que **agrupan**: las que tienen subcarpetas que agrupan, o más de una
 * obra (una temporada con 25 episodios). La carpeta de una película, con su única
 * obra dentro, no: en `Pelis` habría 176 entradas de una sola película que no
 * aportan nada al árbol. Sus obras se ven al elegir la carpeta de arriba.
 */
export function esNavegable(nodo: NodoArbol): boolean {
  if (nodo.hoja) return false
  const hojas = nodo.hijos.filter((hijo) => hijo.hoja).length
  return hojas > 1 || nodo.hijos.some(esNavegable)
}

/** Las carpetas navegables que cuelgan directamente de `nodo`. */
export function subcarpetas(nodo: NodoArbol): NodoArbol[] {
  return nodo.hijos.filter(esNavegable)
}

/**
 * Las obras que se ven al elegir `nodo`: sus hojas directas y las de sus carpetas
 * no navegables (las de cada película), a cualquier profundidad. Las de sus
 * subcarpetas navegables no: esas se ven entrando en ellas.
 */
export function obrasDe(nodo: NodoArbol): Obra[] {
  const obras: Obra[] = []
  const recorrer = (actual: NodoArbol, carpetaDeLaObra: string | null) => {
    for (const hijo of actual.hijos) {
      if (hijo.hoja) {
        obras.push({ nodo: hijo, ...tituloLegible(carpetaDeLaObra ?? hijo.nombre) })
      } else if (!esNavegable(hijo)) {
        // La carpeta de una película: su nombre es el título de la obra.
        recorrer(hijo, hijo.nombre)
      }
    }
  }
  recorrer(nodo, null)
  return obras.sort((a, b) => a.titulo.localeCompare(b.titulo, 'es'))
}

/** Busca un nodo por su ruta (la ruta es única en todo el árbol). */
export function buscar(raices: NodoArbol[], ruta: string): NodoArbol | null {
  for (const raiz of raices) {
    if (raiz.ruta === ruta) return raiz
    const encontrado = buscar(raiz.hijos, ruta)
    if (encontrado) return encontrado
  }
  return null
}

/** Los nodos desde la raíz hasta `ruta`, para la miga de pan. */
export function caminoHasta(raices: NodoArbol[], ruta: string): NodoArbol[] {
  for (const raiz of raices) {
    if (raiz.ruta === ruta) return [raiz]
    const resto = caminoHasta(raiz.hijos, ruta)
    if (resto.length) return [raiz, ...resto]
  }
  return []
}

/** Nombre corto de una carpeta vigilada (`Z:\Pelis` → `Pelis`). */
export function nombreCarpeta(nodo: NodoArbol, esRaiz: boolean): string {
  if (!esRaiz) return nodo.nombre
  const partes = nodo.ruta.split(/[\\/]/).filter(Boolean)
  return partes[partes.length - 1] ?? nodo.ruta
}

// --- Filtros por estado --------------------------------------------------------------

export type Filtro = 'TODAS' | 'TRADUCIR' | 'FUSIONAR' | 'DUAL' | 'SIN_ORIGEN' | 'SOLO_VIDEO' | 'ERROR'

export const FILTROS: { clave: Filtro; texto: string }[] = [
  { clave: 'TODAS', texto: 'Todas' },
  { clave: 'TRADUCIR', texto: 'Traducir' },
  { clave: 'FUSIONAR', texto: 'Fusionar' },
  { clave: 'DUAL', texto: 'Bilingües' },
  { clave: 'SIN_ORIGEN', texto: 'Falta ES/EN' },
  { clave: 'SOLO_VIDEO', texto: 'Solo vídeo' },
  { clave: 'ERROR', texto: 'Con error' },
]

export function cumpleFiltro(nodo: NodoArbol, filtro: Filtro): boolean {
  const pendiente = nodo.estado_obra === 'PENDIENTE'
  switch (filtro) {
    case 'TODAS':
      return true
    case 'TRADUCIR':
      return pendiente && nodo.subtitulo_coreano_id === null
    case 'FUSIONAR':
      return pendiente && nodo.subtitulo_coreano_id !== null
    case 'DUAL':
      return nodo.estado_obra === 'DUAL'
    case 'SIN_ORIGEN':
      return nodo.estado_obra === 'SIN_ORIGEN'
    case 'SOLO_VIDEO':
      return nodo.estado_obra === 'SIN_SUBTITULOS'
    case 'ERROR':
      return nodo.estado_obra === 'ERROR'
  }
}

/** Si la obra puede pasar a bilingüe ahora mismo (tiene origen ES/EN). */
export function esGenerable(nodo: NodoArbol): boolean {
  return nodo.subtitulo_origen_id !== null
}
