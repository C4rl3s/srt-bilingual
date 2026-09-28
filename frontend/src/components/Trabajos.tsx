import { useState } from 'react'
import { usePersistente } from '../hooks/usePersistente'
import type { Cupo, Trabajo } from '../types'
import { haceCuanto, numero, porcentaje, tituloDeRuta } from '../utils/formato'
import { IconoAviso } from './Iconos'

interface Props {
  trabajos: Trabajo[]
  cupo: Cupo | null
  onGenerar: (subtituloIds: number[], forzarTraduccion?: boolean) => Promise<void>
  numFusionables: number
  onVerFusionables: () => void
}

/**
 * Los trabajos de generación: los que necesitan una decisión, los que están en
 * marcha y el historial, más el cupo del proveedor.
 */
export function Trabajos({ trabajos, cupo, onGenerar, numFusionables, onVerFusionables }: Props) {
  // Los fallos que el usuario ya ha visto y descartado. No se borran del
  // historial (son la cuenta del cupo); solo dejan de pedir atención.
  const [descartados, setDescartados] = usePersistente<number[]>('trabajos.descartados', [])
  const [error, setError] = useState<string | null>(null)

  const activos = trabajos.filter((t) => t.activo)
  // Un fallo necesita decisión mientras no haya otro trabajo más nuevo para el
  // mismo origen (si ya se reintentó, el fallo queda solo como historial).
  const pendientes = trabajos.filter(
    (t) =>
      t.estado === 'FAILED' &&
      !descartados.includes(t.id) &&
      !trabajos.some((otro) => otro.id > t.id && otro.subtitulo_id === t.subtitulo_id),
  )
  const historial = trabajos.filter((t) => !t.activo && !pendientes.includes(t))

  async function reintentar(trabajo: Trabajo, forzar: boolean) {
    if (trabajo.subtitulo_id === null) return
    setError(null)
    try {
      await onGenerar([trabajo.subtitulo_id], forzar)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="pagina pagina--con-lateral">
      <main className="pagina-principal">
        <h1>Trabajos</h1>
        {error && <p className="aviso aviso--error">{error}</p>}

        {pendientes.length > 0 && (
          <section className="seccion">
            <h2 className="rotulo rotulo--aviso">Necesitan tu decisión · {pendientes.length}</h2>
            {pendientes.map((trabajo) => {
              const fusionMala = trabajo.modo === 'FUSION' && trabajo.calidad_alineacion !== null
              return (
                <div key={trabajo.id} className="tarjeta-aviso">
                  <IconoAviso tamano={22} />
                  <div className="tarjeta-aviso-texto">
                    <b>
                      {tituloDeRuta(trabajo.ruta_origen)} ·{' '}
                      {fusionMala ? 'la fusión no casa' : 'no se pudo generar'}
                    </b>
                    <p>{trabajo.mensaje_error}</p>
                  </div>
                  <button
                    className="boton-secundario"
                    onClick={() => setDescartados((previos) => [...previos, trabajo.id])}
                  >
                    Descartar
                  </button>
                  <button className="boton-primario" onClick={() => reintentar(trabajo, fusionMala)}>
                    {fusionMala ? 'Traducir con DeepL' : 'Reintentar'}
                  </button>
                </div>
              )
            })}
          </section>
        )}

        <section className="seccion">
          <h2 className="rotulo">En curso y en cola · {activos.length}</h2>
          {activos.length === 0 && <p className="texto-2">No hay nada en marcha.</p>}
          {activos.map((trabajo) => (
            <div key={trabajo.id} className="fila-trabajo">
              <span className={`modo modo--${trabajo.modo === 'FUSION' ? 'fusion' : 'traduccion'}`}>
                {trabajo.modo === 'FUSION' ? 'Fusión' : 'Traducción'}
              </span>
              <div className="fila-trabajo-texto">
                <b>{tituloDeRuta(trabajo.ruta_origen)}</b>
                <span className="texto-2">
                  {trabajo.estado === 'QUEUED'
                    ? 'En cola'
                    : `${numero(trabajo.bloques_procesados)} de ${numero(trabajo.bloques_totales)} bloques` +
                      (trabajo.modo === 'TRADUCCION' ? ` · ${numero(trabajo.num_caracteres)} caracteres` : '')}
                </span>
              </div>
              <div className="barra barra--gruesa">
                <div className="barra-relleno" style={{ width: `${porcentaje(trabajo)}%` }} />
              </div>
              <span className="cifra">{porcentaje(trabajo)} %</span>
            </div>
          ))}
        </section>

        <section className="seccion">
          <h2 className="rotulo">Historial</h2>
          {historial.length === 0 ? (
            <p className="texto-2">Aún no has generado ningún bilingüe.</p>
          ) : (
            <div className="tabla-contenedor">
              <table className="tabla">
                <thead>
                  <tr>
                    <th>Obra</th>
                    <th>Modo</th>
                    <th>Caracteres</th>
                    <th>Calidad</th>
                    <th>Resultado</th>
                    <th>Terminado</th>
                  </tr>
                </thead>
                <tbody>
                  {historial.map((trabajo) => (
                    <tr key={trabajo.id}>
                      <td>
                        <b>{tituloDeRuta(trabajo.ruta_origen)}</b>
                      </td>
                      <td>{trabajo.modo === 'FUSION' ? 'Fusión' : 'Traducción'}</td>
                      <td className="cifra">{numero(trabajo.num_caracteres)}</td>
                      <td>{trabajo.calidad_alineacion?.toFixed(2).replace('.', ',') ?? '—'}</td>
                      <td className={trabajo.estado === 'FAILED' ? 'texto-aviso' : undefined}>
                        {trabajo.estado === 'DONE' ? 'Hecho' : 'Falló'}
                      </td>
                      <td className="texto-2">{haceCuanto(trabajo.finalizado_en)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      <aside className="pagina-lateral">
        {cupo && (
          <section className="tarjeta-lateral">
            <h2>Cupo de {cupo.proveedor === 'deepl' ? 'DeepL' : cupo.proveedor}</h2>
            {cupo.limite !== null ? (
              <>
                <div className="cifra-grande">
                  {numero(cupo.limite - cupo.usados)} <span>libres</span>
                </div>
                <div className="barra barra--gruesa">
                  <div className="barra-relleno" style={{ width: `${(100 * cupo.usados) / cupo.limite}%` }} />
                </div>
                <p className="texto-2">
                  {numero(cupo.usados)} usados de {numero(cupo.limite)}.
                </p>
              </>
            ) : (
              <p className="texto-2">{numero(cupo.usados)} caracteres usados.</p>
            )}
          </section>
        )}
        {numFusionables > 0 && (
          <section className="tarjeta-lateral">
            <h2>Sin gastar cupo</h2>
            <p className="texto-2">
              {numFusionables} {numFusionables === 1 ? 'obra tiene' : 'obras tienen'} ya subtítulo
              coreano y se {numFusionables === 1 ? 'puede' : 'pueden'} fusionar gratis.
            </p>
            <button className="enlace" onClick={onVerFusionables}>
              Ver las fusionables
            </button>
          </section>
        )}
      </aside>
    </div>
  )
}
