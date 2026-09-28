import { useState } from 'react'
import type { EstadoObra, NodoArbol } from '../types'

/** Cómo se pinta cada estado de obra en la hoja. */
const INSIGNIA: Record<EstadoObra, { texto: string; clase: string }> = {
  DUAL: { texto: '✅ dual', clase: 'badge--dual' },
  PENDIENTE: { texto: '⏳ pendiente', clase: '' },
  SIN_ORIGEN: { texto: '⚠ sin subs ES/EN', clase: 'badge--aviso' },
  SIN_SUBTITULOS: { texto: '⚠ sin subs detectados', clase: 'badge--aviso' },
  ERROR: { texto: '✖ error', clase: 'badge--error' },
}

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
    const insignia = INSIGNIA[nodo.estado_obra ?? 'SIN_SUBTITULOS']
    return (
      <li className="nodo nodo--hoja" style={{ paddingLeft: `${nivel * 1.25}rem` }}>
        <span className="nodo-nombre">{nodo.nombre}</span>
        <span className="nodo-idiomas">{nodo.idiomas.join(' · ')}</span>
        {/* Con coreano ya existente, el bilingüe saldrá de fusionar, sin gastar cuota. */}
        {nodo.subtitulo_coreano_id !== null && nodo.estado_obra === 'PENDIENTE' && (
          <span className="badge">🇰🇷 fusionable</span>
        )}
        <span className={`badge ${insignia.clase}`}>{insignia.texto}</span>
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
          {nodo.num_sin_subtitulos > 0 && ` · ${nodo.num_sin_subtitulos} sin subs`}
          {nodo.num_sin_origen > 0 && ` · ${nodo.num_sin_origen} sin ES/EN`}
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
  /** Qué decir cuando no hay nada que pintar; lo decide `App` según el contexto. */
  mensajeVacio: string
}

/** Bloque inferior: la biblioteca, de la carpeta raíz hasta cada capítulo. */
export function ArbolSubtitulos({ arbol, cargando, mensajeVacio }: Props) {
  if (cargando) return <p className="vacio">Cargando…</p>

  const sinContenido = arbol.length === 0 || arbol.every((raiz) => raiz.hijos.length === 0)
  if (sinContenido) return <p className="vacio">{mensajeVacio}</p>

  return (
    <ul className="arbol">
      {arbol.map((raiz) => (
        <Nodo key={raiz.ruta} nodo={raiz} nivel={0} />
      ))}
    </ul>
  )
}
