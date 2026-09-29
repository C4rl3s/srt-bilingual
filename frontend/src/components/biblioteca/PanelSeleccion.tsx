import { useState } from 'react'
import type { EstadoCupo } from '../../types'
import type { Obra } from '../../utils/biblioteca'
import { libreTotal, nombreProveedor, repartir } from '../../utils/cupos'
import { caracteres as formatoCaracteres, numero } from '../../utils/formato'
import { IconoCerrar } from '../Iconos'

interface Props {
  obras: Obra[]
  cupos: EstadoCupo[]
  onGenerar: (subtituloIds: number[]) => Promise<void>
  onQuitar: (ruta: string) => void
  onQuitarTodas: () => void
}

/**
 * Columna derecha en modo selección: qué se va a generar, cómo, con qué proveedor
 * y cuánto cupo gastará, antes de pulsar nada.
 */
export function PanelSeleccion({ obras, cupos, onGenerar, onQuitar, onQuitarTodas }: Props) {
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Las fusiones no gastan cupo: solo cuentan las que se traducen.
  const aTraducir = obras.filter((obra) => obra.nodo.subtitulo_coreano_id === null)
  const caracteres = aTraducir.reduce((suma, obra) => suma + obra.nodo.num_caracteres, 0)
  // Con alguna pista sin extraer, el total es una estimación (por arriba).
  const exactos = aTraducir.every((obra) => obra.nodo.caracteres_exactos)

  // Previsión del reparto entre proveedores, en el mismo orden en que el backend
  // creará los trabajos (ver `utils/cupos.ts`).
  const previstos = repartir(
    cupos,
    aTraducir.map((obra) => ({
      caracteres: obra.nodo.num_caracteres,
      conGuia: obra.nodo.ruta_guia !== null,
    })),
  )
  const proveedorDe = new Map(aTraducir.map((obra, i) => [obra.nodo.ruta, previstos[i]]))
  const sinCupo = aTraducir.filter((obra) => proveedorDe.get(obra.nodo.ruta) === null)

  const libre = libreTotal(cupos)
  const limiteTotal = cupos
    .filter((c) => c.disponible && c.limite !== null)
    .reduce((suma, c) => suma + (c.limite ?? 0), 0)
  const gastadoTotal = cupos
    .filter((c) => c.disponible && c.limite !== null)
    .reduce((suma, c) => suma + c.usados + c.reservados, 0)
  const ancho = (n: number) => `${limiteTotal ? Math.min(100, (100 * n) / limiteTotal) : 0}%`

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
          const proveedor = proveedorDe.get(obra.nodo.ruta)
          const idioma = obra.nodo.idioma_origen === 'EN' ? 'inglés' : 'español'
          return (
            <li key={obra.nodo.ruta} className="fila-pista">
              <span
                className={`fila-pista-barra fila-pista-barra--${fusion ? 'coreano' : 'origen'}`}
                aria-hidden="true"
              />
              <div className="fila-pista-texto">
                <b className="recortar">{obra.titulo}</b>
                <div className={proveedor === null ? 'texto-aviso' : 'texto-2'}>
                  {fusion
                    ? 'Fusión con el coreano'
                    : proveedor === null
                      ? 'Sin cupo en ningún proveedor'
                      : `Traducción · ${idioma} · ${nombreProveedor(proveedor ?? null)}`}
                </div>
              </div>
              <span className="cifra">
                {fusion ? '0' : formatoCaracteres(obra.nodo.num_caracteres, obra.nodo.caracteres_exactos)}
              </span>
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
            <span className="texto-2">Se enviarán a traducir</span>
            <b>{formatoCaracteres(caracteres, exactos)} caracteres</b>
          </div>
          {!exactos && (
            <div className="texto-3">
              ≈: alguna obra sale de una pista del vídeo aún sin extraer. La cifra es por
              arriba y se corrige al extraerla.
            </div>
          )}
          {libre !== null && (
            <>
              <div className="calidad-fila">
                <span className="texto-2">Cupo libre después, entre todos</span>
                <b>{numero(Math.max(0, libre - caracteres))}</b>
              </div>
              <div className="barra barra--doble" aria-hidden="true">
                <div className="barra-usado" style={{ width: ancho(gastadoTotal) }} />
                <div className="barra-relleno" style={{ width: ancho(caracteres) }} />
              </div>
              <div className="texto-3">Gris: ya usado o reservado · naranja: esta selección</div>
            </>
          )}
          {sinCupo.length > 0 && (
            <p className="texto-aviso">
              {sinCupo.length === 1 ? 'Una obra no cabe' : `${sinCupo.length} obras no caben`} en
              ningún proveedor: no se generará.
            </p>
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
