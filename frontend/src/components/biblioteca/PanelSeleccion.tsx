import { useState } from 'react'
import type { Cupo } from '../../types'
import type { Obra } from '../../utils/biblioteca'
import { numero } from '../../utils/formato'
import { IconoCerrar } from '../Iconos'

interface Props {
  obras: Obra[]
  cupo: Cupo | null
  onGenerar: (subtituloIds: number[]) => Promise<void>
  onQuitar: (ruta: string) => void
  onQuitarTodas: () => void
}

/**
 * Columna derecha en modo selección: qué se va a generar, cómo y cuánto cupo
 * gastará, antes de pulsar nada.
 */
export function PanelSeleccion({ obras, cupo, onGenerar, onQuitar, onQuitarTodas }: Props) {
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Las fusiones no gastan cupo: solo cuentan las que se traducen.
  const aTraducir = obras.filter((obra) => obra.nodo.subtitulo_coreano_id === null)
  const caracteres = aTraducir.reduce((suma, obra) => suma + obra.nodo.num_caracteres, 0)
  const libres = cupo?.limite != null ? cupo.limite - cupo.usados : null
  const pasaDelCupo = libres !== null && caracteres > libres

  async function generar() {
    setEnviando(true)
    setError(null)
    try {
      // `!` porque solo se pueden seleccionar obras con origen (ver `esGenerable`).
      await onGenerar(obras.map((obra) => obra.nodo.subtitulo_origen_id!))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <aside className="detalle" aria-label="Selección">
      <div className="detalle-cabecera">
        <h2>
          {obras.length} {obras.length === 1 ? 'seleccionada' : 'seleccionadas'}
        </h2>
        {obras.length > 0 && (
          <button className="boton-pequeno" onClick={onQuitarTodas}>
            Quitar todas
          </button>
        )}
      </div>

      {obras.length === 0 && (
        <p className="texto-2">Marca las obras que quieras pasar a bilingüe.</p>
      )}

      <ul className="seleccion-lista">
        {obras.map((obra) => {
          const fusion = obra.nodo.subtitulo_coreano_id !== null
          return (
            <li key={obra.nodo.ruta} className="fila-pista">
              <span
                className={`fila-pista-barra fila-pista-barra--${fusion ? 'coreano' : 'origen'}`}
                aria-hidden="true"
              />
              <div className="fila-pista-texto">
                <b className="recortar">{obra.titulo}</b>
                <div className="texto-2">
                  {fusion ? 'Fusión con el coreano' : `Traducción · ${obra.nodo.idioma_origen === 'EN' ? 'inglés' : 'español'}`}
                </div>
              </div>
              <span className="cifra">{fusion ? '0' : numero(obra.nodo.num_caracteres)}</span>
              <button
                className="boton-icono"
                onClick={() => onQuitar(obra.nodo.ruta)}
                aria-label={`Quitar ${obra.titulo}`}
              >
                <IconoCerrar tamano={14} />
              </button>
            </li>
          )
        })}
      </ul>

      {obras.length > 0 && (
        <div className="resumen-cupo">
          <div className="calidad-fila">
            <span className="texto-2">Se enviarán a DeepL</span>
            <b>{numero(caracteres)} caracteres</b>
          </div>
          {libres !== null && cupo?.limite && (
            <>
              <div className="calidad-fila">
                <span className="texto-2">Cupo después</span>
                <b className={pasaDelCupo ? 'texto-aviso' : undefined}>
                  {pasaDelCupo ? 'no alcanza' : `${numero(libres - caracteres)} libres`}
                </b>
              </div>
              <div className="barra barra--doble">
                <div className="barra-usado" style={{ width: `${(100 * cupo.usados) / cupo.limite}%` }} />
                <div
                  className="barra-relleno"
                  style={{ width: `${Math.min(100, (100 * caracteres) / cupo.limite)}%` }}
                />
              </div>
              <div className="texto-3">Gris: ya usado · naranja: esta selección</div>
            </>
          )}
        </div>
      )}

      {error && <p className="aviso aviso--error">{error}</p>}

      <p className="texto-2">
        Se procesan de uno en uno, en segundo plano. Puedes seguir navegando: el progreso
        está en Trabajos.
      </p>

      <div className="detalle-pie">
        <button
          className="boton-primario boton-ancho"
          disabled={obras.length === 0 || enviando}
          onClick={generar}
        >
          {enviando
            ? 'Enviando…'
            : `Generar ${obras.length} ${obras.length === 1 ? 'bilingüe' : 'bilingües'}`}
        </button>
      </div>
    </aside>
  )
}
