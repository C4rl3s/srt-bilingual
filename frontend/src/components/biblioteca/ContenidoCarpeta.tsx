import type { NodoArbol } from '../../types'
import {
  FILTROS,
  type Filtro,
  type Obra,
  cumpleFiltro,
  esGenerable,
  nombreCarpeta,
  obrasDe,
  subcarpetas,
} from '../../utils/biblioteca'
import { numero, tituloLegible, tonoDe } from '../../utils/formato'
import { IconoCarpeta, IconoLista, IconoMarca, IconoMosaico, IconoSeleccionar } from '../Iconos'

export type Vista = 'mosaico' | 'lista'

interface Props {
  carpeta: NodoArbol
  camino: NodoArbol[]
  vista: Vista
  onVista: (vista: Vista) => void
  filtro: Filtro
  onFiltro: (filtro: Filtro) => void
  obraElegida: string | null
  onElegirObra: (obra: Obra) => void
  onEntrar: (ruta: string) => void
  seleccionando: boolean
  onSeleccionando: (activo: boolean) => void
  seleccion: string[]
  onAlternarSeleccion: (ruta: string) => void
  /** Texto de progreso por id de subtítulo de origen, para las obras en marcha. */
  progreso: Map<number, string>
}

/** Columna central: lo que hay en la carpeta elegida, en mosaico o en lista. */
export function ContenidoCarpeta(props: Props) {
  const { carpeta, camino, vista, filtro } = props
  const obras = obrasDe(carpeta)
  const carpetas = subcarpetas(carpeta)
  const visibles = obras.filter((obra) => cumpleFiltro(obra.nodo, filtro))
  // Solo se ofrecen los filtros que tienen algo: un «Con error 0» es ruido.
  const filtros = FILTROS.map((f) => ({
    ...f,
    cuenta: obras.filter((obra) => cumpleFiltro(obra.nodo, f.clave)).length,
  })).filter((f) => f.clave === 'TODAS' || f.cuenta > 0)

  return (
    <section className="contenido" aria-label="Contenido de la carpeta">
      <div className="contenido-cabecera">
        <div className="miga">
          {camino.map((nodo, i) => (
            <span key={nodo.ruta}>
              {i > 0 && ' › '}
              {i < camino.length - 1 ? (
                <button className="enlace-miga" onClick={() => props.onEntrar(nodo.ruta)}>
                  {nombreCarpeta(nodo, i === 0)}
                </button>
              ) : (
                nombreCarpeta(nodo, i === 0)
              )}
            </span>
          ))}
        </div>
        <div className="contenido-titulo">
          <h1>{nombreCarpeta(carpeta, camino.length === 1)}</h1>
          <span className="texto-2">
            {carpetas.length > 0 && `${carpetas.length} carpetas · `}
            {obras.length} {obras.length === 1 ? 'obra' : 'obras'}
          </span>
          <div className="hueco" />
          {obras.some((obra) => esGenerable(obra.nodo)) && (
            <button
              className={`boton-secundario ${props.seleccionando ? 'boton-secundario--activo' : ''}`}
              aria-pressed={props.seleccionando}
              onClick={() => props.onSeleccionando(!props.seleccionando)}
            >
              <IconoSeleccionar tamano={16} />
              {props.seleccionando ? 'Seleccionando' : 'Seleccionar'}
            </button>
          )}
          <div className="conmutador" role="group" aria-label="Vista">
            <button
              aria-pressed={vista === 'mosaico'}
              aria-label="Mosaico"
              onClick={() => props.onVista('mosaico')}
            >
              <IconoMosaico />
            </button>
            <button
              aria-pressed={vista === 'lista'}
              aria-label="Lista"
              onClick={() => props.onVista('lista')}
            >
              <IconoLista />
            </button>
          </div>
        </div>
      </div>

      {obras.length > 0 && (
        <div className="filtros" role="group" aria-label="Filtrar por estado">
          {filtros.map((f) => (
            <button
              key={f.clave}
              className={`chip ${filtro === f.clave ? 'chip--activo' : ''}`}
              aria-pressed={filtro === f.clave}
              onClick={() => props.onFiltro(f.clave)}
            >
              {f.texto} <span className="chip-cuenta">{f.cuenta}</span>
            </button>
          ))}
        </div>
      )}

      <div className={vista === 'mosaico' ? 'mosaico' : 'lista'}>
        {filtro === 'TODAS' &&
          carpetas.map((sub) => (
            <TarjetaCarpeta key={sub.ruta} nodo={sub} vista={vista} onEntrar={props.onEntrar} />
          ))}
        {visibles.map((obra) => (
          <TarjetaObra key={obra.nodo.ruta} obra={obra} {...props} />
        ))}
      </div>

      {visibles.length === 0 && carpetas.length === 0 && (
        <p className="vacio">
          {obras.length === 0 ? 'Esta carpeta está vacía.' : 'Nada con este filtro.'}
        </p>
      )}
    </section>
  )
}

function TarjetaCarpeta({
  nodo,
  vista,
  onEntrar,
}: {
  nodo: NodoArbol
  vista: Vista
  onEntrar: (ruta: string) => void
}) {
  // `[Erai-raws] Moonrise - 01 ~ 18 [1080p NF…]` → «Moonrise - 01 ~ 18».
  const { titulo, anio } = tituloLegible(nodo.nombre)
  return (
    <button
      className={`tarjeta tarjeta--${vista} tarjeta--carpeta`}
      onClick={() => onEntrar(nodo.ruta)}
      title={nodo.nombre}
    >
      <div className="tarjeta-imagen" style={{ background: tonoDe(nodo.ruta) }}>
        <span className="tarjeta-icono">
          <IconoCarpeta tamano={vista === 'mosaico' ? 34 : 22} />
        </span>
        {vista === 'mosaico' && (
          <span className="tarjeta-titulo">
            {titulo}
            {anio && <span className="tarjeta-anio">{anio}</span>}
          </span>
        )}
      </div>
      <div className="tarjeta-pie">
        {vista === 'lista' && <span className="tarjeta-titulo-lista">{titulo}</span>}
        <span className="texto-2">
          {nodo.num_dual} / {nodo.num_obras} bilingües
        </span>
      </div>
    </button>
  )
}

function TarjetaObra({ obra, ...props }: Props & { obra: Obra }) {
  const { nodo } = obra
  const { vista } = props
  const generable = esGenerable(nodo)
  const marcada = props.seleccion.includes(nodo.ruta)
  const elegida = props.obraElegida === nodo.ruta
  const seleccionable = props.seleccionando && generable

  const alPulsar = () => {
    if (props.seleccionando) {
      if (generable) props.onAlternarSeleccion(nodo.ruta)
    } else {
      props.onElegirObra(obra)
    }
  }

  const clases = [
    'tarjeta',
    `tarjeta--${vista}`,
    elegida && !props.seleccionando ? 'tarjeta--elegida' : '',
    marcada ? 'tarjeta--marcada' : '',
    props.seleccionando && !generable ? 'tarjeta--apagada' : '',
  ].join(' ')

  return (
    <button
      className={clases}
      onClick={alPulsar}
      aria-pressed={props.seleccionando ? marcada : elegida}
      aria-label={`${obra.titulo}${obra.anio ? ` (${obra.anio})` : ''}`}
    >
      <div className="tarjeta-imagen" style={{ background: tonoDe(nodo.ruta) }}>
        {seleccionable && (
          <span className={`casilla ${marcada ? 'casilla--marcada' : ''}`} aria-hidden="true">
            {marcada && <IconoMarca tamano={16} />}
          </span>
        )}
        {vista === 'mosaico' && (
          <span className="tarjeta-titulo">
            {obra.titulo}
            {obra.anio && <span className="tarjeta-anio">{obra.anio}</span>}
          </span>
        )}
      </div>
      <div className="tarjeta-pie">
        {vista === 'lista' && (
          <span className="tarjeta-titulo-lista">
            {obra.titulo}
            {obra.anio && <span className="texto-3"> · {obra.anio}</span>}
          </span>
        )}
        <Pistas nodo={nodo} />
        <span className="tarjeta-nota">{nota(nodo, props.progreso)}</span>
      </div>
    </button>
  )
}

/** Las dos etiquetas «ES → KO»: el origen propuesto y si el coreano ya existe. */
export function Pistas({ nodo }: { nodo: NodoArbol }) {
  const origen = nodo.idioma_origen ?? (nodo.estado_obra === 'SIN_SUBTITULOS' ? 'MKV' : '—')
  const conOrigen = nodo.idioma_origen !== null
  const conCoreano = nodo.subtitulo_coreano_id !== null || nodo.estado_obra === 'DUAL'
  return (
    <span className="pistas" aria-hidden="true">
      <span className={`pista ${conOrigen ? 'pista--origen' : 'pista--vacia'}`}>{origen}</span>
      <span className="pista-flecha">→</span>
      <span className={`pista ${conCoreano ? 'pista--coreano' : 'pista--coreano-falta'}`}>KO</span>
    </span>
  )
}

function nota(nodo: NodoArbol, progreso: Map<number, string>): string {
  const enMarcha = nodo.subtitulo_origen_id !== null && progreso.get(nodo.subtitulo_origen_id)
  if (enMarcha) return enMarcha
  switch (nodo.estado_obra) {
    case 'DUAL':
      return 'hecho'
    case 'PENDIENTE':
      return nodo.subtitulo_coreano_id !== null ? 'fusión' : `${numero(nodo.num_caracteres)} c.`
    case 'SIN_ORIGEN':
      return 'falta ES/EN'
    case 'SIN_SUBTITULOS':
      return 'subs en MKV'
    case 'ERROR':
      return 'error'
    default:
      return ''
  }
}
