import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { ArbolSubtitulos } from './components/ArbolSubtitulos'
import { PanelCarpetas } from './components/PanelCarpetas'
import { SelectorCarpeta } from './components/SelectorCarpeta'
import type { Carpeta, Estado, NodoArbol, ResumenEscaneo } from './types'
import './App.css'

type Filtro = Estado | 'TODOS'

function App() {
  const [carpetas, setCarpetas] = useState<Carpeta[]>([])
  const [arbol, setArbol] = useState<NodoArbol[]>([])
  const [filtro, setFiltro] = useState<Filtro>('TODOS')
  const [cargandoArbol, setCargandoArbol] = useState(true)
  const [escaneando, setEscaneando] = useState(false)
  const [selectorAbierto, setSelectorAbierto] = useState(false)
  const [resumen, setResumen] = useState<ResumenEscaneo | null>(null)
  const [error, setError] = useState<string | null>(null)

  // `useCallback` mantiene la misma función entre renders mientras no cambie
  // `filtro`. Importa porque se usa como dependencia del `useEffect` de abajo:
  // sin esto se recrearía en cada render y el efecto se dispararía en bucle.
  const cargarArbol = useCallback(async () => {
    setCargandoArbol(true)
    try {
      setArbol(await api.arbol(filtro === 'TODOS' ? undefined : filtro))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargandoArbol(false)
    }
  }, [filtro])

  const cargarCarpetas = useCallback(async () => {
    try {
      setCarpetas(await api.listarCarpetas())
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    cargarCarpetas()
  }, [cargarCarpetas])

  useEffect(() => {
    cargarArbol()
  }, [cargarArbol])

  async function anadirCarpeta(ruta: string) {
    setError(null)
    try {
      await api.anadirCarpeta(ruta)
      setSelectorAbierto(false)
      await cargarCarpetas()
    } catch (e) {
      // El modal sigue abierto para que se pueda elegir otra carpeta.
      setError((e as Error).message)
    }
  }

  async function marcarCarpeta(carpeta: Carpeta, activa: boolean) {
    // Actualización optimista: la casilla responde al instante y luego se
    // confirma contra el servidor.
    setCarpetas((previas) =>
      previas.map((c) => (c.id === carpeta.id ? { ...c, activa } : c)),
    )
    try {
      await api.marcarCarpeta(carpeta.id, activa)
    } catch (e) {
      setError((e as Error).message)
      await cargarCarpetas() // deshacer: recargamos la verdad del servidor
    }
  }

  async function borrarCarpeta(carpeta: Carpeta) {
    if (!confirm(`¿Dejar de vigilar ${carpeta.ruta}?\n\nSe borrarán sus subtítulos del inventario (los ficheros del disco no se tocan).`)) {
      return
    }
    try {
      await api.borrarCarpeta(carpeta.id)
      await Promise.all([cargarCarpetas(), cargarArbol()])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function escanear() {
    setEscaneando(true)
    setError(null)
    setResumen(null)
    try {
      setResumen(await api.escanear())
      await Promise.all([cargarCarpetas(), cargarArbol()])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEscaneando(false)
    }
  }

  return (
    <main className="app">
      <h1>srt-bilingual</h1>

      {error && (
        <p className="aviso aviso--error" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      {resumen && (
        <p className="aviso aviso--ok" onClick={() => setResumen(null)}>
          {resumen.carpetas} carpeta(s): {resumen.nuevos} nuevos, {resumen.actualizados}{' '}
          actualizados, {resumen.sin_cambios} sin cambios, {resumen.traducidos} con dual,{' '}
          {resumen.errores} con error.
        </p>
      )}

      <PanelCarpetas
        carpetas={carpetas}
        escaneando={escaneando}
        onMarcar={marcarCarpeta}
        onBorrar={borrarCarpeta}
        onAnadir={() => setSelectorAbierto(true)}
        onEscanear={escanear}
      />

      <section className="panel">
        <header className="panel-cabecera">
          <h2>Biblioteca</h2>
          <select
            className="filtro"
            value={filtro}
            onChange={(evento) => setFiltro(evento.target.value as Filtro)}
          >
            <option value="TODOS">Todo</option>
            <option value="TRANSLATED">Solo con dual</option>
            <option value="PENDING">Solo pendientes</option>
            <option value="ERROR">Solo con error</option>
          </select>
        </header>

        <ArbolSubtitulos arbol={arbol} cargando={cargandoArbol} />
      </section>

      {selectorAbierto && (
        <SelectorCarpeta
          onCerrar={() => setSelectorAbierto(false)}
          onSeleccionar={anadirCarpeta}
        />
      )}
    </main>
  )
}

export default App
