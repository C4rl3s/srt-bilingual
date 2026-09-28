import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PropuestaRenombrado } from '../types'
import { nombreDeRuta, tituloDeRuta } from '../utils/formato'
import { IconoMarca } from './Iconos'

interface Props {
  /** Avisa de cuántas propuestas quedan, para el contador de la pestaña. */
  onCambio: (numPropuestas: number) => void
}

const CONFLICTOS: Record<string, string> = {
  EXISTE: 'Ya existe ese nombre',
  DUPLICADO: 'Otro subtítulo quiere el mismo nombre',
  ERROR_DISCO: 'El disco rechazó el cambio',
}

type Filtro = 'TODAS' | 'FORZADOS' | 'CONFLICTOS'

/**
 * Renombrar a la nomenclatura de Plex: la lista `actual → nuevo`, con casillas.
 * Nada se toca hasta pulsar el botón, y nunca se sobrescribe un fichero.
 */
export function Renombrado({ onCambio }: Props) {
  const [propuestas, setPropuestas] = useState<PropuestaRenombrado[] | null>(null)
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  const [filtro, setFiltro] = useState<Filtro>('TODAS')
  const [aplicando, setAplicando] = useState(false)
  const [mensaje, setMensaje] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const lista = await api.propuestasRenombrado()
      setPropuestas(lista)
      // Por defecto, todas las que se pueden aplicar.
      setMarcadas(new Set(lista.filter((p) => !p.conflicto).map((p) => p.subtitulo_id)))
      onCambio(lista.filter((p) => !p.conflicto).length)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [onCambio])

  useEffect(() => {
    cargar()
  }, [cargar])

  function alternar(id: number) {
    // Un `Set` no se muta: se crea uno nuevo, para que React vea el cambio.
    setMarcadas((previas) => {
      const nuevas = new Set(previas)
      if (nuevas.has(id)) nuevas.delete(id)
      else nuevas.add(id)
      return nuevas
    })
  }

  async function aplicar() {
    setAplicando(true)
    setError(null)
    try {
      const resultado = await api.renombrar([...marcadas])
      setMensaje(
        `${resultado.renombrados.length} renombrados` +
          (resultado.rechazados.length ? `, ${resultado.rechazados.length} no se pudieron` : ''),
      )
      await cargar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setAplicando(false)
    }
  }

  if (!propuestas) {
    return <div className="pagina">{error ? <p className="aviso aviso--error">{error}</p> : <p className="vacio">Cargando…</p>}</div>
  }

  const esForzado = (p: PropuestaRenombrado) => p.ruta_nueva.includes('.forced.')
  const visibles = propuestas.filter((p) =>
    filtro === 'FORZADOS' ? esForzado(p) : filtro === 'CONFLICTOS' ? p.conflicto !== null : true,
  )
  const conflictos = propuestas.filter((p) => p.conflicto).length

  return (
    <div className="pagina pagina--con-barra">
      <div className="pagina-cabecera">
        <div>
          <h1>Renombrar para Plex</h1>
          <p className="texto-2 parrafo">
            Subtítulos junto al vídeo cuyo nombre no dice su idioma, o dice uno que no es.
            Plex los muestra como «Desconocido». Solo se renombra lo que marques, y nunca se
            sobrescribe un fichero.
          </p>
        </div>
        <div className="filtros" role="group" aria-label="Filtrar">
          {(
            [
              ['TODAS', 'Todas', propuestas.length],
              ['FORZADOS', 'Forzados', propuestas.filter(esForzado).length],
              ['CONFLICTOS', 'Conflictos', conflictos],
            ] as const
          ).map(([clave, texto, cuenta]) => (
            <button
              key={clave}
              className={`chip ${filtro === clave ? 'chip--activo' : ''}`}
              aria-pressed={filtro === clave}
              onClick={() => setFiltro(clave)}
            >
              {texto} <span className="chip-cuenta">{cuenta}</span>
            </button>
          ))}
        </div>
      </div>

      {mensaje && (
        <p className="aviso aviso--ok" onClick={() => setMensaje(null)}>
          {mensaje}
        </p>
      )}
      {error && <p className="aviso aviso--error">{error}</p>}

      {propuestas.length === 0 ? (
        <p className="vacio">No hay nada que renombrar: todos los subtítulos dicen bien su idioma.</p>
      ) : (
        <div className="tabla-contenedor">
          <table className="tabla tabla--renombrado">
            <thead>
              <tr>
                <th aria-label="Marcar" />
                <th>Obra</th>
                <th>Nombre actual → nombre nuevo</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((p) => {
                const marcada = marcadas.has(p.subtitulo_id)
                const actual = nombreDeRuta(p.ruta_actual)
                const nuevo = nombreDeRuta(p.ruta_nueva)
                // El sufijo nuevo (`.eng.srt`, `.spa.forced.srt`) es lo que cambia.
                const corte = nuevo.search(/\.(spa|eng|kor)(\.|$)/)
                return (
                  <tr key={p.subtitulo_id} className={p.conflicto ? 'fila-apagada' : undefined}>
                    <td>
                      <button
                        role="checkbox"
                        aria-checked={marcada}
                        aria-label={`Renombrar ${actual}`}
                        className={`casilla casilla--tabla ${marcada ? 'casilla--marcada' : ''}`}
                        disabled={p.conflicto !== null}
                        onClick={() => alternar(p.subtitulo_id)}
                      >
                        {marcada && <IconoMarca tamano={14} />}
                      </button>
                    </td>
                    <td>
                      <b>{tituloDeRuta(p.ruta_actual)}</b>
                    </td>
                    <td className="celda-nombres">
                      <span className="nombre-actual">{actual}</span>
                      <span className="nombre-nuevo">
                        {corte > 0 ? nuevo.slice(0, corte) : nuevo}
                        {corte > 0 && <mark>{nuevo.slice(corte)}</mark>}
                      </span>
                    </td>
                    <td className={p.conflicto ? 'texto-aviso' : 'texto-2'}>
                      {p.conflicto
                        ? CONFLICTOS[p.conflicto]
                        : esForzado(p)
                          ? 'Forzado encubierto'
                          : 'El nombre no dice bien su idioma'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {propuestas.length > 0 && (
        <div className="barra-accion">
          <div>
            <b>
              {marcadas.size} de {propuestas.length} marcados
            </b>
            {conflictos > 0 && (
              <div className="texto-2">
                {conflictos === 1 ? 'El que tiene' : `Los ${conflictos} con`} conflicto se quedan como están
              </div>
            )}
          </div>
          <div className="hueco" />
          <button className="boton-texto" onClick={() => setMarcadas(new Set())}>
            Desmarcar todos
          </button>
          <button className="boton-primario" disabled={marcadas.size === 0 || aplicando} onClick={aplicar}>
            {aplicando ? 'Renombrando…' : `Renombrar ${marcadas.size}`}
          </button>
        </div>
      )}
    </div>
  )
}
