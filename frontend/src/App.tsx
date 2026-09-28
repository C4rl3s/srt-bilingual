import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { Biblioteca } from './components/biblioteca/Biblioteca'
import { Cabecera, type Seccion } from './components/Cabecera'
import { Carpetas } from './components/Carpetas'
import { Renombrado } from './components/Renombrado'
import { Trabajos } from './components/Trabajos'
import { useTrabajos } from './hooks/useTrabajos'
import type { Carpeta, EstadoCupo, NodoArbol, ResumenEscaneo } from './types'
import './App.css'

/**
 * Esqueleto de la aplicación: la cabecera con sus pestañas y la sección activa.
 *
 * Aquí viven los datos que comparten varias secciones (el árbol, las carpetas,
 * los trabajos y el cupo); cada sección recibe lo suyo por props. Sin router: con
 * cuatro secciones, un `useState` basta y se entiende de un vistazo.
 */
function App() {
  const [seccion, setSeccion] = useState<Seccion>('biblioteca')
  const [arbol, setArbol] = useState<NodoArbol[]>([])
  const [cargandoArbol, setCargandoArbol] = useState(true)
  const [carpetas, setCarpetas] = useState<Carpeta[]>([])
  const [cupos, setCupos] = useState<EstadoCupo[]>([])
  const [escaneando, setEscaneando] = useState(false)
  const [resumen, setResumen] = useState<ResumenEscaneo | null>(null)
  const [numPropuestas, setNumPropuestas] = useState(0)
  const [arbolAbiertoMovil, setArbolAbiertoMovil] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // `useCallback` mantiene la misma función entre renders. Importa porque se usan
  // como dependencia de efectos: si se recrearan en cada render, esos efectos se
  // dispararían en bucle.
  const cargarArbol = useCallback(async () => {
    try {
      setArbol(await api.arbol())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargandoArbol(false)
    }
  }, [])

  const cargarCarpetas = useCallback(async () => {
    try {
      setCarpetas(await api.listarCarpetas())
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  const cargarCupos = useCallback(async () => {
    try {
      setCupos(await api.cupos())
    } catch {
      setCupos([]) // sin cupos la app funciona igual; solo no los enseña
    }
  }, [])

  const cargarPropuestas = useCallback(async () => {
    try {
      setNumPropuestas((await api.propuestasRenombrado()).filter((p) => !p.conflicto).length)
    } catch {
      // El contador de la pestaña es un extra: si falla, se queda como estaba.
    }
  }, [])

  // Cuando termina el último trabajo en marcha hay obras nuevas en DUAL y cupo
  // gastado: se recargan las dos cosas.
  const alTerminarTrabajos = useCallback(() => {
    cargarArbol()
    cargarCupos()
  }, [cargarArbol, cargarCupos])

  const { trabajos, recargar: recargarTrabajos } = useTrabajos(alTerminarTrabajos)

  useEffect(() => {
    cargarArbol()
    cargarCarpetas()
    cargarCupos()
    cargarPropuestas()
  }, [cargarArbol, cargarCarpetas, cargarCupos, cargarPropuestas])

  async function escanear(carpetaIds?: number[]) {
    setEscaneando(true)
    setError(null)
    try {
      setResumen(await api.escanear(carpetaIds))
      await Promise.all([cargarArbol(), cargarCarpetas(), cargarPropuestas()])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEscaneando(false)
    }
  }

  async function generar(subtituloIds: number[], forzarTraduccion = false) {
    const respuesta = await api.traducir(subtituloIds, forzarTraduccion)
    if (respuesta.rechazados.length) {
      setError(respuesta.rechazados.map((r) => r.motivo).join(' · '))
    }
    // Empieza el sondeo (la cabecera y el panel ven el progreso) y se refrescan los
    // cupos: los trabajos nuevos ya reservan el suyo.
    await Promise.all([recargarTrabajos(), cargarCupos()])
  }

  // Obras que se pueden fusionar gratis, para el aviso de la pantalla de trabajos.
  const numFusionables = contarFusionables(arbol)

  return (
    <div className="app">
      <Cabecera
        seccion={seccion}
        onCambiar={setSeccion}
        trabajos={trabajos}
        cupos={cupos}
        numPropuestas={numPropuestas}
        onAbrirArbol={() => {
          setSeccion('biblioteca')
          setArbolAbiertoMovil(true)
        }}
      />

      {error && (
        <p className="aviso aviso--error aviso--flotante" role="alert" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      {seccion === 'biblioteca' && (
        <Biblioteca
          arbol={arbol}
          cargando={cargandoArbol}
          trabajos={trabajos}
          cupos={cupos}
          escaneando={escaneando}
          onEscanear={() => escanear()}
          onGestionar={() => setSeccion('carpetas')}
          onGenerar={generar}
          arbolAbiertoMovil={arbolAbiertoMovil}
          onCerrarArbolMovil={() => setArbolAbiertoMovil(false)}
        />
      )}
      {seccion === 'trabajos' && (
        <Trabajos
          trabajos={trabajos}
          cupos={cupos}
          onGenerar={generar}
          numFusionables={numFusionables}
          onVerFusionables={() => setSeccion('biblioteca')}
        />
      )}
      {seccion === 'renombrado' && <Renombrado onCambio={setNumPropuestas} />}
      {seccion === 'carpetas' && (
        <Carpetas
          carpetas={carpetas}
          onRecargar={async () => {
            await Promise.all([cargarCarpetas(), cargarArbol()])
          }}
          escaneando={escaneando}
          resumen={resumen}
          onEscanear={escanear}
          onVolver={() => setSeccion('biblioteca')}
        />
      )}
    </div>
  )
}

function contarFusionables(nodos: NodoArbol[]): number {
  return nodos.reduce(
    (total, nodo) =>
      total +
      (nodo.hoja
        ? Number(nodo.estado_obra === 'PENDIENTE' && nodo.subtitulo_coreano_id !== null)
        : contarFusionables(nodo.hijos)),
    0,
  )
}

export default App
