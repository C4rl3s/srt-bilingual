import { useEffect, useState } from 'react'
import './App.css'

type BackendStatus = 'cargando' | 'ok' | 'error'

function App() {
  const [status, setStatus] = useState<BackendStatus>('cargando')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: { status: string }) => {
        setStatus(data.status === 'ok' ? 'ok' : 'error')
      })
      .catch(() => setStatus('error'))
  }, [])

  const label =
    status === 'cargando'
      ? 'Conectando…'
      : status === 'ok'
        ? 'Backend: ok ✅'
        : 'Backend: sin conexión ❌'

  return (
    <main className="app">
      <h1>srt-bilingual</h1>
      <p>Generador de subtítulos bilingües.</p>
      <p className={`status status--${status}`}>{label}</p>
    </main>
  )
}

export default App
