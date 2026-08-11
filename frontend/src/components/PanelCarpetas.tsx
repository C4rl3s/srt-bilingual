import type { Carpeta } from '../types'

interface Props {
  carpetas: Carpeta[]
  escaneando: boolean
  onMarcar: (carpeta: Carpeta, activa: boolean) => void
  onBorrar: (carpeta: Carpeta) => void
  onAnadir: () => void
  onEscanear: () => void
}

/** Fecha ISO (UTC) del backend → hora local legible. */
function formatearFecha(iso: string | null): string {
  if (!iso) return 'sin escanear'
  // El backend guarda UTC pero SQLite no conserva la zona, así que llega sin
  // offset. Se lo añadimos para que el navegador no lo lea como hora local.
  const fecha = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return fecha.toLocaleString()
}

/** Bloque superior: las carpetas vigiladas y el botón de escanear. */
export function PanelCarpetas({
  carpetas,
  escaneando,
  onMarcar,
  onBorrar,
  onAnadir,
  onEscanear,
}: Props) {
  const marcadas = carpetas.filter((carpeta) => carpeta.activa).length

  return (
    <section className="panel">
      <header className="panel-cabecera">
        <h2>Carpetas</h2>
        <button className="boton-secundario" onClick={onAnadir}>
          + Añadir
        </button>
      </header>

      {carpetas.length === 0 ? (
        <p className="vacio">
          Todavía no vigilas ninguna carpeta. Pulsa <b>+ Añadir</b> y elige dónde tienes
          los subtítulos.
        </p>
      ) : (
        <ul className="carpetas">
          {carpetas.map((carpeta) => (
            <li key={carpeta.id} className="carpeta">
              <label className="carpeta-check">
                <input
                  type="checkbox"
                  checked={carpeta.activa}
                  onChange={(evento) => onMarcar(carpeta, evento.target.checked)}
                />
                <span className="carpeta-ruta">{carpeta.ruta}</span>
              </label>

              <span className="carpeta-datos">
                <span className="badge badge--dual">{carpeta.num_dual} dual</span>
                <span className="badge">{carpeta.num_pendientes} pendientes</span>
                {carpeta.num_errores > 0 && (
                  <span className="badge badge--error">{carpeta.num_errores} con error</span>
                )}
                <span className="carpeta-fecha">{formatearFecha(carpeta.ultimo_escaneo)}</span>
              </span>

              <button
                className="boton-icono"
                onClick={() => onBorrar(carpeta)}
                title="Dejar de vigilar esta carpeta"
                aria-label={`Borrar ${carpeta.ruta}`}
              >
                🗑
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="panel-pie">
        <button
          className="boton-primario"
          disabled={escaneando || marcadas === 0}
          onClick={onEscanear}
        >
          {escaneando ? 'Escaneando…' : `Escanear (${marcadas})`}
        </button>
      </div>
    </section>
  )
}
