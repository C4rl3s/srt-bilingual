import { type KeyboardEvent, type PointerEvent, useRef } from 'react'

interface Props {
  /** Ancho actual, en píxeles, del panel que redimensiona. */
  ancho: number
  minimo: number
  maximo: number
  /** Ancho al hacer doble clic: el de siempre. */
  porDefecto: number
  onCambiar: (ancho: number) => void
  /**
   * De qué lado del tirador está el panel. `izquierda` (el árbol): arrastrar hacia la
   * derecha lo ensancha. `derecha` (el detalle): arrastrar hacia la derecha lo estrecha.
   */
  panel: 'izquierda' | 'derecha'
  etiqueta: string
}

// Paso de las flechas del teclado; con Mayúsculas, el cuádruple.
const PASO_TECLADO = 16

/**
 * Borde arrastrable entre dos columnas, para ensanchar o estrechar un panel.
 *
 * Usa *pointer events* (ratón, dedo y lápiz con el mismo código) con
 * `setPointerCapture`: mientras se arrastra, el tirador sigue recibiendo los
 * movimientos aunque el puntero salga de él, que al arrastrar deprisa pasa enseguida.
 *
 * Es también un `separator` accesible: se enfoca con Tab y se mueve con las flechas.
 */
export function Tirador({ ancho, minimo, maximo, porDefecto, onCambiar, panel, etiqueta }: Props) {
  // Dónde empezó el arrastre: posición del puntero y ancho de entonces. En una ref y
  // no en estado porque cambia en cada movimiento y no tiene que repintar nada.
  const inicio = useRef<{ x: number; ancho: number } | null>(null)

  const limitar = (valor: number) => Math.round(Math.min(maximo, Math.max(minimo, valor)))
  const sentido = panel === 'izquierda' ? 1 : -1

  function alPulsar(evento: PointerEvent<HTMLDivElement>) {
    if (evento.button !== 0) return
    evento.currentTarget.setPointerCapture(evento.pointerId)
    inicio.current = { x: evento.clientX, ancho }
    // Mientras se arrastra, el cursor de redimensionar en toda la página y sin
    // seleccionar texto por el camino.
    document.body.classList.add('arrastrando')
  }

  function alMover(evento: PointerEvent<HTMLDivElement>) {
    if (!inicio.current) return
    onCambiar(limitar(inicio.current.ancho + sentido * (evento.clientX - inicio.current.x)))
  }

  function alSoltar(evento: PointerEvent<HTMLDivElement>) {
    inicio.current = null
    document.body.classList.remove('arrastrando')
    // Al pulsarlo con el ratón queda enfocado, y el navegador lo pinta como foco de
    // teclado: el borde se quedaría resaltado. Quien use el teclado llega con Tab.
    evento.currentTarget.blur()
  }

  function alTeclear(evento: KeyboardEvent<HTMLDivElement>) {
    const paso = evento.shiftKey ? PASO_TECLADO * 4 : PASO_TECLADO
    const cambios: Record<string, number> = {
      ArrowRight: ancho + sentido * paso,
      ArrowLeft: ancho - sentido * paso,
      Home: minimo,
      End: maximo,
    }
    if (evento.key in cambios) {
      evento.preventDefault()
      onCambiar(limitar(cambios[evento.key]))
    }
  }

  return (
    <div
      className={`tirador tirador--${panel}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={etiqueta}
      aria-valuenow={ancho}
      aria-valuemin={minimo}
      aria-valuemax={maximo}
      tabIndex={0}
      title="Arrastra para cambiar el ancho · doble clic: ancho normal"
      onPointerDown={alPulsar}
      onPointerMove={alMover}
      onPointerUp={alSoltar}
      onPointerCancel={alSoltar}
      onDoubleClick={() => onCambiar(porDefecto)}
      onKeyDown={alTeclear}
    />
  )
}
