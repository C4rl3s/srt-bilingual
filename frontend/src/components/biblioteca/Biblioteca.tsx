import { type CSSProperties, useEffect, useState } from 'react'
import { usePersistente } from '../../hooks/usePersistente'
import type { EstadoCupo, NodoArbol, Trabajo } from '../../types'
import { type Filtro, buscar, caminoHasta, nombreCarpeta, obrasDe } from '../../utils/biblioteca'
import { porcentaje } from '../../utils/formato'
import { ArbolCarpetas } from './ArbolCarpetas'
import { ContenidoCarpeta, type Vista } from './ContenidoCarpeta'
import { PanelDetalle } from './PanelDetalle'
import { PanelSeleccion } from './PanelSeleccion'
import { Tirador } from './Tirador'

// Anchos de los laterales, en píxeles: el de siempre y los límites al arrastrar.
const ARBOL = { porDefecto: 284, minimo: 200, maximo: 600 }
const PANEL = { porDefecto: 380, minimo: 320, maximo: 760 }
// Lo que ocupa el árbol plegado (su franja de iconos), y lo mínimo que se deja al
// contenido central para que el mosaico siga teniendo al menos una columna.
const ARBOL_PLEGADO = 56
const MINIMO_CENTRO = 320

/** El ancho de la ventana, al día: los límites de los laterales dependen de él. */
function useAnchoVentana(): number {
  const [ancho, setAncho] = useState(window.innerWidth)
  useEffect(() => {
    const alCambiar = () => setAncho(window.innerWidth)
    window.addEventListener('resize', alCambiar)
    return () => window.removeEventListener('resize', alCambiar)
  }, [])
  return ancho
}

interface Props {
  arbol: NodoArbol[]
  cargando: boolean
  trabajos: Trabajo[]
  cupos: EstadoCupo[]
  escaneando: boolean
  onEscanear: () => void
  onGestionar: () => void
  onGenerar: (subtituloIds: number[], forzarTraduccion?: boolean, proveedor?: string) => Promise<void>
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
  // Anchos de las columnas laterales, que el usuario ajusta arrastrando su borde.
  const [anchoArbol, setAnchoArbol] = usePersistente('ancho.arbol', ARBOL.porDefecto)
  const [anchoPanel, setAnchoPanel] = usePersistente('ancho.panel', PANEL.porDefecto)
  const ventana = useAnchoVentana()

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

  // Cada lateral puede crecer hasta su máximo, pero sin dejar el contenido central
  // por debajo de su mínimo: el límite depende de la ventana y del otro lateral. Si
  // la ventana encoge, el ancho mostrado se recorta sin perder el que eligió el
  // usuario, que vuelve al agrandarla.
  const ocupadoArbol = plegado ? ARBOL_PLEGADO : anchoArbol
  const maximoArbol = Math.max(
    ARBOL.minimo,
    Math.min(ARBOL.maximo, ventana - (hayPanel ? anchoPanel : 0) - MINIMO_CENTRO),
  )
  const maximoPanel = Math.max(
    PANEL.minimo,
    Math.min(PANEL.maximo, ventana - ocupadoArbol - MINIMO_CENTRO),
  )
  const arbolVisible = Math.min(anchoArbol, maximoArbol)
  const panelVisible = Math.min(anchoPanel, maximoPanel)
  // Los anchos llegan al CSS como variables: así las reglas de pantalla estrecha (donde
  // los laterales son cajones) pueden ignorarlos sin pelearse con un `style` en línea.
  const anchos = {
    '--ancho-arbol': `${arbolVisible}px`,
    '--ancho-panel': `${panelVisible}px`,
  } as CSSProperties

  return (
    <div className={`biblioteca ${hayPanel ? 'biblioteca--con-panel' : ''}`} style={anchos}>
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
      {!plegado && (
        <Tirador
          panel="izquierda"
          etiqueta="Ancho del árbol de carpetas"
          ancho={arbolVisible}
          minimo={ARBOL.minimo}
          maximo={maximoArbol}
          porDefecto={ARBOL.porDefecto}
          onCambiar={setAnchoArbol}
        />
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

      {hayPanel && (
        <Tirador
          panel="derecha"
          etiqueta="Ancho del panel de la obra"
          ancho={panelVisible}
          minimo={PANEL.minimo}
          maximo={maximoPanel}
          porDefecto={PANEL.porDefecto}
          onCambiar={setAnchoPanel}
        />
      )}

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
            onGenerar={(id, forzar, proveedor) => props.onGenerar([id], forzar, proveedor)}
            onCerrar={() => setRutaObra(null)}
          />
        )
      )}
    </div>
  )
}
