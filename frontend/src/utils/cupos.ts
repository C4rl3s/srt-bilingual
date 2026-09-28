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

/**
 * Qué proveedor traducirá cada obra, en orden, o `null` si no cabe en ninguno.
 *
 * **Es una previsión**: reproduce la regla del backend (`eleccion.Asignador`)
 * para que la interfaz lo diga antes de pulsar. Quien decide de verdad es el
 * backend al crear los trabajos; si mientras tanto cambia el cupo, puede elegir
 * otro. Si se cambia la regla allí, hay que cambiarla aquí.
 */
export function repartir(cupos: EstadoCupo[], caracteres: number[]): (string | null)[] {
  const asignado = new Map<string, number>()
  return caracteres.map((cantidad) => {
    for (const cupo of cupos) {
      if (!cupo.disponible) continue
      const libre = cupo.libre === null ? null : cupo.libre - (asignado.get(cupo.proveedor) ?? 0)
      if (libre === null || libre >= cantidad * MARGEN) {
        asignado.set(cupo.proveedor, (asignado.get(cupo.proveedor) ?? 0) + cantidad)
        return cupo.proveedor
      }
    }
    return null
  })
}
