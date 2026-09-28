// Formato de números, fechas y nombres para mostrar. Funciones puras: sin estado
// ni React, así que se pueden usar en cualquier componente.

import type { Trabajo } from '../types'

const numeros = new Intl.NumberFormat('es-ES')

/** 64751 → «64.751». `Intl` ya sabe los separadores de cada idioma. */
export function numero(n: number): string {
  return numeros.format(n)
}

/**
 * Fecha ISO del backend → «hace 2 h», «ayer, 22:15»…
 *
 * El backend guarda UTC pero SQLite no conserva la zona, así que llega sin offset.
 * Se le añade la `Z` para que el navegador no la lea como hora local.
 */
export function haceCuanto(iso: string | null): string {
  if (!iso) return 'nunca'
  const fecha = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  const minutos = Math.round((Date.now() - fecha.getTime()) / 60_000)
  if (minutos < 1) return 'ahora mismo'
  if (minutos < 60) return `hace ${minutos} min`
  if (minutos < 24 * 60) return `hace ${Math.round(minutos / 60)} h`
  return fecha.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

export interface Titulo {
  titulo: string
  anio: string | null
}

/**
 * Nombre de carpeta o fichero de una descarga → título legible.
 *
 * `Mercy (2026) [1080p] [WEBRip] [5.1] [YTS.BZ]` → Mercy · 2026
 * `Se7en(1995)1080p.BrRip.x264.YIFY` → Se7en · 1995
 * `Dust.Bunny.2025.1080p.WEBRip…` → Dust Bunny · 2025
 * `[Erai-Raws] Shingeki No Kyojin - 01` → Shingeki No Kyojin - 01
 *
 * Se corta en el año: lo que va detrás (calidad, códec, grupo) es ruido para un
 * humano. Sin año, se deja el nombre limpio de corchetes.
 */
export function tituloLegible(nombre: string): Titulo {
  let limpio = nombre.replace(/\[[^\]]*\]/g, ' ')
  // Los nombres con puntos en vez de espacios (`Dust.Bunny.2025`) se separan.
  if (!limpio.includes(' ')) limpio = limpio.replace(/[._]/g, ' ')
  limpio = limpio.replace(/\s+/g, ' ').trim()

  const conAnio = limpio.match(/^(.*?)[\s(.]*((?:19|20)\d{2})(?!\d)/)
  if (conAnio && conAnio[1].trim()) {
    return { titulo: conAnio[1].replace(/[\s(.-]+$/, '').trim(), anio: conAnio[2] }
  }
  return { titulo: limpio || nombre, anio: null }
}

/** Nombre del fichero o carpeta final de una ruta de Windows o POSIX. */
export function nombreDeRuta(ruta: string): string {
  const partes = ruta.split(/[\\/]/).filter(Boolean)
  return partes[partes.length - 1] ?? ruta
}

/**
 * Título de la obra de un trabajo o de un renombrado, a partir de la ruta de su
 * subtítulo: la carpeta que lo contiene, saltando la subcarpeta `Subs`.
 *
 * Si esa carpeta no parece de una película (no tiene año: `Pelis`, cuando el .srt
 * está suelto en la raíz), manda el nombre del fichero.
 */
export function tituloDeRuta(ruta: string): string {
  const partes = ruta.split(/[\\/]/).filter(Boolean)
  const fichero = (partes.pop() ?? ruta).replace(/\.srt$/i, '')
  let carpeta = partes.pop() ?? ruta
  if (carpeta.toLowerCase() === 'subs') carpeta = partes.pop() ?? carpeta
  const deCarpeta = tituloLegible(carpeta)
  const deFichero = tituloLegible(fichero)
  return !deCarpeta.anio && deFichero.anio ? deFichero.titulo : deCarpeta.titulo
}

// Tonos de los pósteres de pega: mientras no haya carátulas reales, cada obra
// tiene un color estable derivado de su nombre, para que no bailen al recargar.
const TONOS = ['#2A2F36', '#23323A', '#352631', '#3B3322', '#26342B', '#30293A', '#1F3029', '#37302A', '#2B2B2B', '#3A2E24']

export function tonoDe(clave: string): string {
  let hash = 0
  for (const letra of clave) hash = (hash * 31 + letra.charCodeAt(0)) | 0
  return TONOS[Math.abs(hash) % TONOS.length]
}

/** Avance de un trabajo, de 0 a 100. */
export function porcentaje(trabajo: Trabajo): number {
  if (!trabajo.bloques_totales) return 0
  return Math.round((100 * trabajo.bloques_procesados) / trabajo.bloques_totales)
}
