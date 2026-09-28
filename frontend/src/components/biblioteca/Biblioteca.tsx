import { useState } from 'react'
import { usePersistente } from '../../hooks/usePersistente'
import type { EstadoCupo, NodoArbol, Trabajo } from '../../types'
import { type Filtro, buscar, caminoHasta, nombreCarpeta, obrasDe } from '../../utils/biblioteca'
import { porcentaje } from '../../utils/formato'
import { ArbolCarpetas } from './ArbolCarpetas'
import { ContenidoCarpeta, type Vista } from './ContenidoCarpeta'
import { PanelDetalle } from './PanelDetalle'
import { PanelSeleccion } from './PanelSeleccion'

interface Props {
  arbol: NodoArbol[]
  cargando: boolean
  trabajos: Trabajo[]
  cupos: EstadoCupo[]
  escaneando: boolean
  onEscanear: () => void
  onGestionar: () => void
  onGenerar: (subtituloIds: number[], forzarTraduccion?: boolean) => Promise<void>
  /** En pantallas estrechas el árbol es un cajón que se abre desde la cabecera. */
  arbolAbiertoMovil: boolean
  onCerrarArbolMovil: () => void
}

/**
 * La biblioteca en tres columnas: árbol de carpetas, contenido de la elegida y
 * panel de la obra (o de la selección).
 */
export function Biblioteca(props: Props) {
  const { arbol, trabajos } = props

  // Preferencias que sobreviven a recargar la página.
  const [plegado, setPlegado] = usePersistente('arbol.plegado', false)
  const [abiertas, setAbiertas] = usePersistente<string[]>('arbol.abiertas', [])
  const [vistas, setVistas] = usePersistente<Record<string, Vista>>('vistas', {})
  const [rutaCarpeta, setRutaCarpeta] = usePersistente<string | null>('carpeta', null)

  const [filtro, setFiltro] = useState<Filtro>('TODAS')
  const [rutaObra, setRutaObra] = useState<string | null>(null)
  const [seleccionando, setSeleccionando] = useState(false)
  const [seleccion, setSeleccion] = useState<string[]>([])

  if (props.cargando && arbol.length === 0) return <p className="vacio">Cargando la biblioteca…</p>
  if (arbol.length === 0) {
    return (
      <div className="vacio vacio--grande">
        <p>Todavía no vigilas ninguna carpeta.</p>
        <button className="boton-primario" onClick={props.onGestionar}>
          Añadir una carpeta
        </button>
      </div>
    )
  }

  // La carpeta guardada puede no existir ya (se quitó, o cambió el disco): se cae
  // a la primera raíz.
  const carpeta = (rutaCarpeta && buscar(arbol, rutaCarpeta)) || arbol[0]
  const camino = caminoHasta(arbol, carpeta.ruta)
  const obras = obrasDe(carpeta)
  const obraElegida = obras.find((obra) => obra.nodo.ruta === rutaObra) ?? null
  const seleccionadas = obras.filter((obra) => seleccion.includes(obra.nodo.ruta))

  // Vista por defecto: lista si la mayoría de sus obras están sueltas en la propia
  // carpeta (los episodios de una temporada), mosaico si casi todas viven cada una
  // en su carpeta (películas). `Pelis` tiene alguna suelta en la raíz, y no por eso
  // deja de ser una carpeta de películas.
  const sueltas = carpeta.hijos.filter((hijo) => hijo.hoja).length
  const vista = vistas[carpeta.ruta] ?? (sueltas > obras.length / 2 ? 'lista' : 'mosaico')

  // Progreso de los trabajos en marcha, por id de su subtítulo de origen.
  const progreso = new Map<number, string>()
  for (const trabajo of trabajos) {
    if (trabajo.activo && trabajo.subtitulo_id !== null) {
      progreso.set(trabajo.subtitulo_id, trabajo.estado === 'QUEUED' ? 'en cola' : `${porcentaje(trabajo)} %`)
    }
  }
  const trabajoDe = (id: number | null) =>
    trabajos.find((trabajo) => trabajo.activo && trabajo.subtitulo_id === id)

  function entrar(ruta: string) {
    setRutaCarpeta(ruta)
    setRutaObra(null)
    setFiltro('TODAS')
    setSeleccion([])
    // Al entrar en una carpeta se despliegan sus antecesoras, para verla en el árbol.
    const antecesoras = caminoHasta(arbol, ruta).slice(0, -1).map((nodo) => nodo.ruta)
    setAbiertas((previas) => [...new Set([...previas, ...antecesoras])])
    props.onCerrarArbolMovil()
  }

  function alternarAbierta(ruta: string) {
    setAbiertas((previas) =>
      previas.includes(ruta) ? previas.filter((r) => r !== ruta) : [...previas, ruta],
    )
  }

  function alternarSeleccion(ruta: string) {
    setSeleccion((previa) =>
      previa.includes(ruta) ? previa.filter((r) => r !== ruta) : [...previa, ruta],
    )
  }

  async function generarSeleccion(ids: number[]) {
    await props.onGenerar(ids)
    setSeleccion([])
    setSeleccionando(false)
  }

  const miga = camino.map((nodo, i) => nombreCarpeta(nodo, i === 0)).join(' › ')
  const hayPanel = seleccionando || obraElegida !== null

  return (
    <div className={`biblioteca ${hayPanel ? 'biblioteca--con-panel' : ''}`}>
      <div className={`arbol-cajon ${props.arbolAbiertoMovil ? 'arbol-cajon--abierto' : ''}`}>
        <ArbolCarpetas
          raices={arbol}
          seleccionada={carpeta.ruta}
          onSeleccionar={entrar}
          abiertas={abiertas}
          onAlternar={alternarAbierta}
          plegado={plegado}
          onPlegar={setPlegado}
          miga={miga}
          escaneando={props.escaneando}
          onEscanear={props.onEscanear}
          onGestionar={props.onGestionar}
        />
      </div>
      {props.arbolAbiertoMovil && (
        <button className="velo" onClick={props.onCerrarArbolMovil} aria-label="Cerrar carpetas" />
      )}

      <ContenidoCarpeta
        carpeta={carpeta}
        camino={camino}
        vista={vista}
        onVista={(nueva) => setVistas((previas) => ({ ...previas, [carpeta.ruta]: nueva }))}
        filtro={filtro}
        onFiltro={setFiltro}
        obraElegida={rutaObra}
        onElegirObra={(obra) => setRutaObra(obra.nodo.ruta)}
        onEntrar={entrar}
        seleccionando={seleccionando}
        onSeleccionando={(activo) => {
          setSeleccionando(activo)
          if (!activo) setSeleccion([])
        }}
        seleccion={seleccion}
        onAlternarSeleccion={alternarSeleccion}
        progreso={progreso}
      />

      {seleccionando ? (
        <PanelSeleccion
          obras={seleccionadas}
          cupos={props.cupos}
          onGenerar={generarSeleccion}
          onQuitar={alternarSeleccion}
          onQuitarTodas={() => setSeleccion([])}
        />
      ) : (
        obraElegida && (
          <PanelDetalle
            obra={obraElegida}
            trabajo={trabajoDe(obraElegida.nodo.subtitulo_origen_id)}
            cupos={props.cupos}
            onGenerar={(id, forzar) => props.onGenerar([id], forzar)}
            onCerrar={() => setRutaObra(null)}
          />
        )
      )}
    </div>
  )
}
