import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EntradaDirectorio, ListadoDirectorio } from '../types'

interface Props {
  onCerrar: () => void
  onSeleccionar: (ruta: string) => void
}

/**
 * Modal para navegar el disco y elegir una carpeta.
 *
 * El navegador no puede darnos la ruta absoluta de una carpeta del sistema (un
 * `<input type="file" webkitdirectory>` solo devuelve rutas relativas), así que
 * la navegación la sirve el backend en `/fs/*` y aquí solo la pintamos.
 */
export function SelectorCarpeta({ onCerrar, onSeleccionar }: Props) {
  const [raices, setRaices] = useState<EntradaDirectorio[]>([])
  const [listado, setListado] = useState<ListadoDirectorio | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)

  // Array de dependencias vacío: se ejecuta una sola vez, al montar.
  useEffect(() => {
    api
      .listarRaices()
      .then(setRaices)
      .catch((e: Error) => setError(e.message))
  }, [])

  async function abrir(ruta: string) {
    setCargando(true)
    setError(null)
    try {
      setListado(await api.navegar(ruta))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargando(false)
    }
  }

  const entradas = listado ? listado.directorios : raices

  return (
    // El clic en el fondo cierra; `stopPropagation` evita que un clic dentro del
    // diálogo burbujee hasta el fondo y lo cierre sin querer.
    <div className="modal-fondo" onClick={onCerrar}>
      <div className="modal" onClick={(evento) => evento.stopPropagation()}>
        <header className="modal-cabecera">
          <h2>Añadir carpeta</h2>
          <button className="boton-icono" onClick={onCerrar} aria-label="Cerrar">
            ✕
          </button>
        </header>

        <div className="modal-ruta">
          <button
            className="boton-secundario"
            disabled={!listado}
            onClick={() => setListado(null)}
            title="Volver a las unidades"
          >
            Unidades
          </button>
          <button
            className="boton-secundario"
            disabled={!listado?.padre}
            onClick={() => listado?.padre && abrir(listado.padre)}
          >
            ↑ Subir
          </button>
          <code>{listado?.ruta ?? 'Elige una unidad'}</code>
        </div>

        {error && <p className="aviso aviso--error">{error}</p>}

        <ul className="listado">
          {cargando && <li className="listado-vacio">Cargando…</li>}
          {!cargando && entradas.length === 0 && (
            <li className="listado-vacio">No hay subcarpetas aquí</li>
          )}
          {!cargando &&
            entradas.map((entrada) => (
              <li key={entrada.ruta}>
                <button className="entrada" onClick={() => abrir(entrada.ruta)}>
                  📁 {entrada.nombre}
                </button>
              </li>
            ))}
        </ul>

        <footer className="modal-pie">
          <button className="boton-secundario" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            className="boton-primario"
            disabled={!listado}
            onClick={() => listado && onSeleccionar(listado.ruta)}
          >
            Seleccionar esta carpeta
          </button>
        </footer>
      </div>
    </div>
  )
}
