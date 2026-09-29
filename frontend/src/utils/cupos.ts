// Cupos de los proveedores de traducción, para mostrarlos y para prever qué
// proveedor traducirá cada obra antes de pedirlo.

import type { EstadoCupo } from '../types'

const NOMBRES: Record<string, string> = { deepl: 'DeepL', azure: 'Azure' }

/** `deepl` → «DeepL». */
export function nombreProveedor(proveedor: string | null): string {
  if (!proveedor) return '—'
  return NOMBRES[proveedor] ?? proveedor
}

/** Libre entre todos los proveedores disponibles con límite conocido. */
export function libreTotal(cupos: EstadoCupo[]): number | null {
  const conLimite = cupos.filter((c) => c.disponible && c.libre !== null)
  if (conLimite.length === 0) return null
  return conLimite.reduce((suma, c) => suma + (c.libre ?? 0), 0)
}

// Holgura sobre lo previsto: la misma que pide el backend (`eleccion.MARGEN`).
const MARGEN = 1.05

/** Una obra a repartir: lo que cuesta y si su serie tiene guía de traducción. */
export interface ObraARepartir {
  caracteres: number
  conGuia: boolean
}

/**
 * Qué proveedor traducirá cada obra, en orden, o `null` si no cabe en ninguno.
 *
 * Regla: el primero con cupo, en el orden configurado; pero si la obra tiene guía,
 * se prueban antes los proveedores que la admiten (en ese mismo orden).
 *
 * **Es una previsión**: reproduce la regla del backend (`eleccion.Asignador`)
 * para que la interfaz lo diga antes de pulsar. Quien decide de verdad es el
 * backend al crear los trabajos; si mientras tanto cambia el cupo, puede elegir
 * otro. Si se cambia la regla allí, hay que cambiarla aquí.
 */
export function repartir(cupos: EstadoCupo[], obras: ObraARepartir[]): (string | null)[] {
  const asignado = new Map<string, number>()
  // `sort` es estable: dentro de cada grupo se conserva el orden configurado.
  const conGuiaPrimero = [...cupos].sort((a, b) => Number(b.admite_guia) - Number(a.admite_guia))
  return obras.map(({ caracteres, conGuia }) => {
    for (const cupo of conGuia ? conGuiaPrimero : cupos) {
      if (cabe(cupo, caracteres, asignado.get(cupo.proveedor) ?? 0)) {
        asignado.set(cupo.proveedor, (asignado.get(cupo.proveedor) ?? 0) + caracteres)
        return cupo.proveedor
      }
    }
    return null
  })
}

/**
 * Si una traducción de `caracteres` cabe en el cupo de un proveedor (disponible y con
 * libre suficiente, con el margen). Un límite desconocido se da por bueno, como en el
 * backend. `yaAsignado`: lo reservado por otras obras de la misma petición.
 */
export function cabe(cupo: EstadoCupo, caracteres: number, yaAsignado = 0): boolean {
  if (!cupo.disponible) return false
  if (cupo.libre === null) return true
  return cupo.libre - yaAsignado >= caracteres * MARGEN
}
