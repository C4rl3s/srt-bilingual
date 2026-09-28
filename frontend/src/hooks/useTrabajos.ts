import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Trabajo } from '../types'

// Cada cuánto se pregunta por los trabajos mientras haya alguno activo.
const INTERVALO_MS = 2000

/**
 * Los trabajos de generación y su progreso, siempre al día.
 *
 * Mientras haya alguno activo (en cola o en curso) se vuelve a preguntar cada dos
 * segundos: es *sondeo* (polling), la forma más simple de ver avanzar una tarea
 * de fondo sin WebSockets. Cuando no queda ninguno activo, se para.
 *
 * `alTerminar` se llama cuando el último trabajo activo acaba: es el momento de
 * recargar el árbol (hay obras nuevas en `DUAL`) y el cupo.
 */
export function useTrabajos(alTerminar: () => void) {
  const [trabajos, setTrabajos] = useState<Trabajo[]>([])
  // `useRef` guarda un valor entre renders sin provocar un render nuevo al
  // cambiarlo: aquí, si en la vuelta anterior había trabajos activos.
  const habiaActivos = useRef(false)

  const cargar = useCallback(async () => {
    try {
      const lista = await api.trabajos()
      setTrabajos(lista)
      const hayActivos = lista.some((trabajo) => trabajo.activo)
      if (habiaActivos.current && !hayActivos) alTerminar()
      habiaActivos.current = hayActivos
    } catch {
      // Un fallo de red puntual no debe tumbar la página: se reintenta al sondear.
    }
  }, [alTerminar])

  useEffect(() => {
    cargar()
  }, [cargar])

  const hayActivos = trabajos.some((trabajo) => trabajo.activo)

  useEffect(() => {
    if (!hayActivos) return
    const temporizador = setInterval(cargar, INTERVALO_MS)
    // La función que devuelve un efecto es su *limpieza*: React la llama antes de
    // volver a ejecutarlo o al desmontar. Sin ella se acumularían intervalos.
    return () => clearInterval(temporizador)
  }, [hayActivos, cargar])

  return { trabajos, recargar: cargar }
}
