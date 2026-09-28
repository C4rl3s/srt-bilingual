import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ProgresoSondeo } from '../types'

// Cada cuánto se pregunta cómo va la lectura de pistas mientras dura.
const INTERVALO_MS = 2000
// Cada cuánto se recarga el árbol mientras tanto: las obras se van completando
// según se leen sus vídeos, pero recargarlo cada 2 s sería tirar trabajo.
const RECARGA_ARBOL_MS = 15000

/**
 * La lectura de pistas que el backend hace en segundo plano tras cada escaneo:
 * `ffprobe` abre la cabecera de cada vídeo nuevo o cambiado (~8 min la primera vez
 * por la red, nada en los siguientes).
 *
 * `seguir()` se llama al terminar un escaneo. El escaneo responde antes de que
 * empiece la lectura, así que no basta con preguntar una vez: se sondea hasta que
 * el backend dice que ha terminado. `alAvanzar` se llama de vez en cuando mientras
 * dura y una última vez al acabar, para recargar el árbol.
 */
export function useSondeo(alAvanzar: () => void) {
  const [progreso, setProgreso] = useState<ProgresoSondeo | null>(null)
  const [siguiendo, setSiguiendo] = useState(false)
  const ultimaRecarga = useRef(0)

  const preguntar = useCallback(async () => {
    try {
      const actual = await api.progresoSondeo()
      setProgreso(actual)
      if (!actual.en_curso) {
        setSiguiendo(false)
        alAvanzar()
      } else if (Date.now() - ultimaRecarga.current > RECARGA_ARBOL_MS) {
        ultimaRecarga.current = Date.now()
        alAvanzar()
      }
    } catch {
      // Un fallo de red puntual: se reintenta en la siguiente vuelta.
    }
  }, [alAvanzar])

  // Al abrir la app puede haber una lectura en marcha de un escaneo anterior.
  useEffect(() => {
    api
      .progresoSondeo()
      .then((actual) => {
        setProgreso(actual)
        if (actual.en_curso) setSiguiendo(true)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!siguiendo) return
    const temporizador = setInterval(preguntar, INTERVALO_MS)
    return () => clearInterval(temporizador)
  }, [siguiendo, preguntar])

  const seguir = useCallback(() => {
    ultimaRecarga.current = Date.now()
    setSiguiendo(true)
  }, [])

  // Mientras se sigue, se da por «en curso» aunque la primera respuesta aún no haya
  // llegado: así la interfaz lo dice desde que termina el escaneo.
  const enCurso = siguiendo || Boolean(progreso?.en_curso)
  return { progreso, enCurso, seguir }
}
