import { useState } from 'react'
import type { NodoArbol } from '../types'

/**
 * Un nodo del árbol, que se pinta a sí mismo y a sus hijos.
 *
 * La recursión en React es literal: el componente se invoca dentro de su propio
 * JSX. Cada instancia guarda su propio `abierto` con `useState`, así que el
 * estado de plegado vive repartido por el árbol y no hay que centralizarlo.
 */
function Nodo({ nodo, nivel }: { nodo: NodoArbol; nivel: number }) {
  // Las dos primeras plantas abiertas: ver la serie y sus temporadas de un vistazo.
  const [abierto, setAbierto] = useState(nivel < 2)

  if (nodo.hoja) {
    return (
      <li className="nodo nodo--hoja" style={{ paddingLeft: `${nivel * 1.25}rem` }}>
        <span className="nodo-nombre">{nodo.nombre}</span>
        <span className="nodo-idiomas">{nodo.idiomas.join(' · ')}</span>
        {nodo.num_errores > 0 ? (
          <span className="badge badge--error">error</span>
        ) : nodo.dual ? (
          <span className="badge badge--dual">✅ dual</span>
        ) : (
          <span className="badge">⏳ pendiente</span>
        )}
      </li>
    )
  }

  return (
    <li className="nodo">
      <button
        className="nodo-carpeta"
        style={{ paddingLeft: `${nivel * 1.25}rem` }}
        onClick={() => setAbierto(!abierto)}
        aria-expanded={abierto}
      >
        <span className="nodo-flecha">{abierto ? '▼' : '▶'}</span>
        <span className="nodo-nombre">{nodo.nombre}</span>
        <span className="nodo-conteo">
          {nodo.num_dual}/{nodo.num_obras} dual
        </span>
      </button>

      {abierto && (
        <ul className="nodo-hijos">
          {nodo.hijos.map((hijo) => (
            // La ruta completa es única en todo el árbol: mejor clave que el índice,
            // que descolocaría el estado de plegado al reordenarse la lista.
            <Nodo key={hijo.ruta} nodo={hijo} nivel={nivel + 1} />
          ))}
        </ul>
      )}
    </li>
  )
}

interface Props {
  arbol: NodoArbol[]
  cargando: boolean
}

/** Bloque inferior: la biblioteca, de la carpeta raíz hasta cada capítulo. */
export function ArbolSubtitulos({ arbol, cargando }: Props) {
  if (cargando) return <p className="vacio">Cargando…</p>

  if (arbol.length === 0) {
    return <p className="vacio">Nada que mostrar. Añade una carpeta y pulsa «Escanear».</p>
  }

  return (
    <ul className="arbol">
      {arbol.map((raiz) => (
        <Nodo key={raiz.ruta} nodo={raiz} nivel={0} />
      ))}
    </ul>
  )
}
