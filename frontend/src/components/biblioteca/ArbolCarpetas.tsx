import type { NodoArbol } from '../../types'
import { nombreCarpeta, subcarpetas } from '../../utils/biblioteca'
import { IconoDesplegar, IconoEscanear, IconoFlecha, IconoPlegar } from '../Iconos'

interface Props {
  raices: NodoArbol[]
  seleccionada: string | null
  onSeleccionar: (ruta: string) => void
  /** Rutas de las carpetas desplegadas (se recuerdan entre visitas). */
  abiertas: string[]
  onAlternar: (ruta: string) => void
  plegado: boolean
  onPlegar: (plegado: boolean) => void
  miga: string
  escaneando: boolean
  onEscanear: () => void
  onGestionar: () => void
}

/**
 * Columna izquierda: el árbol de carpetas de la biblioteca.
 *
 * Plegado se queda en una tira estrecha con el botón para desplegarlo y la ruta
 * actual en vertical: la carpeta elegida no cambia, solo se gana sitio.
 */
export function ArbolCarpetas(props: Props) {
  const { raices, plegado, onPlegar, miga } = props

  if (plegado) {
    return (
      <nav className="arbol arbol--plegado" aria-label="Carpetas de la biblioteca (plegado)">
        <button
          className="boton-icono boton-icono--relleno"
          onClick={() => onPlegar(false)}
          aria-label="Desplegar el árbol"
          aria-expanded="false"
        >
          <IconoDesplegar />
        </button>
        <span className="arbol-miga-vertical">{miga}</span>
      </nav>
    )
  }

  return (
    <nav className="arbol" aria-label="Carpetas de la biblioteca">
      <div className="arbol-cabecera">
        <span className="rotulo">Biblioteca</span>
        <button
          className="boton-icono"
          onClick={props.onEscanear}
          disabled={props.escaneando}
          aria-label={props.escaneando ? 'Escaneando…' : 'Escanear las carpetas marcadas'}
          title="Escanear las carpetas marcadas"
        >
          <span className={props.escaneando ? 'girando' : undefined}>
            <IconoEscanear tamano={16} />
          </span>
        </button>
        <button
          className="boton-icono"
          onClick={() => onPlegar(true)}
          aria-label="Plegar el árbol"
          aria-expanded="true"
        >
          <IconoPlegar />
        </button>
      </div>

      <ul className="arbol-lista" role="tree">
        {raices.map((raiz) => (
          <Rama
            key={raiz.ruta}
            nodo={raiz}
            nivel={0}
            esRaiz
            seleccionada={props.seleccionada}
            onSeleccionar={props.onSeleccionar}
            abiertas={props.abiertas}
            onAlternar={props.onAlternar}
          />
        ))}
      </ul>

      <div className="arbol-pie">
        <button className="enlace" onClick={props.onGestionar}>
          Gestionar carpetas
        </button>
      </div>
    </nav>
  )
}

/**
 * Una carpeta del árbol y, si está desplegada, sus subcarpetas.
 *
 * Componente recursivo: se pinta a sí mismo para cada hija. Solo salen las
 * carpetas que agrupan (ver `esNavegable`): la de cada película no.
 */
interface PropsRama {
  nodo: NodoArbol
  nivel: number
  esRaiz?: boolean
  seleccionada: string | null
  onSeleccionar: (ruta: string) => void
  abiertas: string[]
  onAlternar: (ruta: string) => void
}

function Rama({
  nodo,
  nivel,
  esRaiz = false,
  seleccionada,
  onSeleccionar,
  abiertas,
  onAlternar,
}: PropsRama) {
  const hijas = subcarpetas(nodo)
  const abierta = abiertas.includes(nodo.ruta)
  const elegida = seleccionada === nodo.ruta
  const nombre = nombreCarpeta(nodo, esRaiz)
  // En las raíces se ve el avance (bilingües / obras); en el resto, cuántas hay.
  const cuenta = esRaiz ? `${nodo.num_dual} / ${nodo.num_obras}` : String(nodo.num_obras)

  return (
    <li role="treeitem" aria-expanded={hijas.length ? abierta : undefined} aria-selected={elegida}>
      <div
        className={`rama ${elegida ? 'rama--elegida' : ''}`}
        style={{ paddingLeft: `${8 + nivel * 18}px` }}
      >
        {hijas.length > 0 ? (
          <button
            className={`rama-flecha ${abierta ? 'rama-flecha--abierta' : ''}`}
            onClick={() => onAlternar(nodo.ruta)}
            aria-label={abierta ? `Plegar ${nombre}` : `Desplegar ${nombre}`}
          >
            <IconoFlecha tamano={12} />
          </button>
        ) : (
          <span className="rama-flecha" />
        )}
        <button className="rama-nombre" onClick={() => onSeleccionar(nodo.ruta)} title={nodo.ruta}>
          <span className="recortar">{nombre}</span>
          <span className="rama-cuenta">{cuenta}</span>
        </button>
      </div>

      {abierta && hijas.length > 0 && (
        <ul role="group">
          {hijas.map((hija) => (
            <Rama
              key={hija.ruta}
              nodo={hija}
              nivel={nivel + 1}
              seleccionada={seleccionada}
              onSeleccionar={onSeleccionar}
              abiertas={abiertas}
              onAlternar={onAlternar}
            />
          ))}
        </ul>
      )}
    </li>
  )
}
