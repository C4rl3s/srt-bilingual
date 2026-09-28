import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Carpeta, EntradaDirectorio, ListadoDirectorio, ResumenEscaneo } from '../types'
import { haceCuanto, nombreDeRuta, numero } from '../utils/formato'
import { IconoCarpeta, IconoPapelera, IconoVolver } from './Iconos'

interface Props {
  carpetas: Carpeta[]
  onRecargar: () => Promise<void>
  escaneando: boolean
  resumen: ResumenEscaneo | null
  onEscanear: (carpetaIds?: number[]) => void
  onVolver: () => void
}

/** Las carpetas vigiladas, el escaneo y el explorador para añadir más. */
export function Carpetas({ carpetas, onRecargar, escaneando, resumen, onEscanear, onVolver }: Props) {
  const [error, setError] = useState<string | null>(null)
  // Quitar una carpeta pide confirmación en el propio botón (dos pulsaciones), en
  // vez de un `confirm()` del navegador que bloquea la página.
  const [confirmando, setConfirmando] = useState<number | null>(null)

  async function marcar(carpeta: Carpeta) {
    setError(null)
    try {
      await api.marcarCarpeta(carpeta.id, !carpeta.activa)
      await onRecargar()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function quitar(carpeta: Carpeta) {
    if (confirmando !== carpeta.id) {
      setConfirmando(carpeta.id)
      return
    }
    setConfirmando(null)
    try {
      await api.borrarCarpeta(carpeta.id)
      await onRecargar()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function anadir(ruta: string) {
    setError(null)
    try {
      await api.anadirCarpeta(ruta)
      await onRecargar()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const marcadas = carpetas.filter((c) => c.activa).length

  return (
    <div className="pagina pagina--con-lateral">
      <main className="pagina-principal">
        <div className="pagina-cabecera">
          <div>
            <button className="enlace" onClick={onVolver}>
              <IconoVolver tamano={14} /> Volver a la biblioteca
            </button>
            <h1>Carpetas vigiladas</h1>
          </div>
          <button
            className="boton-primario"
            disabled={escaneando || marcadas === 0}
            onClick={() => onEscanear()}
          >
            {escaneando ? 'Escaneando…' : `Escanear las marcadas (${marcadas})`}
          </button>
        </div>

        {error && (
          <p className="aviso aviso--error" onClick={() => setError(null)}>
            {error}
          </p>
        )}

        {carpetas.length === 0 && (
          <p className="vacio">Todavía no vigilas ninguna carpeta: elige una a la derecha.</p>
        )}

        {carpetas.map((carpeta) => (
          <div key={carpeta.id} className="fila-carpeta">
            <button
              role="switch"
              aria-checked={carpeta.activa}
              aria-label={`Incluir ${carpeta.ruta} al escanear`}
              className={`interruptor ${carpeta.activa ? 'interruptor--on' : ''}`}
              onClick={() => marcar(carpeta)}
            >
              <span />
            </button>
            <div className="fila-carpeta-texto">
              <div>
                <b>{nombreDeRuta(carpeta.ruta)}</b> <code>{carpeta.ruta}</code>
              </div>
              <div className="texto-2">
                {numero(carpeta.num_videos)} vídeos · {numero(carpeta.num_subtitulos)} subtítulos ·{' '}
                {numero(carpeta.num_dual)} bilingües
                {carpeta.num_errores > 0 && ` · ${carpeta.num_errores} con error`}
              </div>
            </div>
            <span className="texto-3">{haceCuanto(carpeta.ultimo_escaneo)}</span>
            <button
              className="boton-secundario"
              disabled={escaneando}
              onClick={() => onEscanear([carpeta.id])}
            >
              Escanear
            </button>
            <button
              className={confirmando === carpeta.id ? 'boton-peligro' : 'boton-icono boton-icono--borde'}
              onClick={() => quitar(carpeta)}
              onBlur={() => setConfirmando(null)}
              aria-label={`Dejar de vigilar ${carpeta.ruta}`}
            >
              {confirmando === carpeta.id ? '¿Quitar? Pulsa otra vez' : <IconoPapelera tamano={16} />}
            </button>
          </div>
        ))}

        {resumen && (
          <section className="tarjeta-escaneo" aria-label="Último escaneo">
            <b>Último escaneo</b>
            <div className="cifras">
              {(
                [
                  [resumen.total, 'subtítulos'],
                  [resumen.videos, 'vídeos'],
                  [resumen.nuevos, 'nuevos'],
                  [resumen.traducidos, 'bilingües'],
                  [resumen.errores, 'errores'],
                ] as const
              ).map(([valor, texto]) => (
                <div key={texto}>
                  <span className="cifra-grande">{numero(valor)}</span>
                  <span className="texto-2">{texto}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      <ExploradorCarpetas vigiladas={carpetas.map((c) => c.ruta)} onElegir={anadir} />
    </div>
  )
}

/**
 * Panel para navegar el disco y elegir una carpeta.
 *
 * El navegador no puede darnos la ruta absoluta de una carpeta del sistema (un
 * `<input type="file" webkitdirectory>` solo devuelve rutas relativas), así que
 * la navegación la sirve el backend en `/fs/*` y aquí solo la pintamos.
 */
function ExploradorCarpetas({
  vigiladas,
  onElegir,
}: {
  vigiladas: string[]
  onElegir: (ruta: string) => Promise<void>
}) {
  const [raices, setRaices] = useState<EntradaDirectorio[]>([])
  const [listado, setListado] = useState<ListadoDirectorio | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Empieza en `true`: hasta que lleguen las unidades, decir «no hay subcarpetas»
  // sería mentir.
  const [cargando, setCargando] = useState(true)

  // Array de dependencias vacío: se ejecuta una sola vez, al montar.
  useEffect(() => {
    api
      .listarRaices()
      .then(setRaices)
      .catch((e: Error) => setError(e.message))
      .finally(() => setCargando(false))
  }, [])

  async function abrir(ruta: string) {
    setCargando(true)
    setError(null)
    try {
      setListado(await api.navegar(ruta))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargando(false)
    }
  }

  const entradas = listado ? listado.directorios : raices
  const yaVigilada = listado !== null && vigiladas.includes(listado.ruta)

  return (
    <aside className="pagina-lateral explorador" aria-label="Añadir carpeta">
      <h2>Añadir carpeta</h2>
      <div className="explorador-ruta">
        <button className="boton-pequeno" disabled={!listado} onClick={() => setListado(null)}>
          Este equipo
        </button>
        {listado?.padre && (
          <button className="boton-pequeno" onClick={() => abrir(listado.padre!)}>
            Subir
          </button>
        )}
        <code className="recortar">{listado?.ruta ?? 'Elige una unidad'}</code>
      </div>

      {error && <p className="aviso aviso--error">{error}</p>}

      <ul className="explorador-lista">
        {cargando && <li className="texto-2">Cargando…</li>}
        {!cargando && entradas.length === 0 && <li className="texto-2">No hay subcarpetas aquí</li>}
        {!cargando &&
          entradas.map((entrada) => (
            <li key={entrada.ruta}>
              <button
                className="entrada"
                onClick={() => abrir(entrada.ruta)}
                disabled={!entrada.accesible}
                title={entrada.motivo ?? undefined}
              >
                <IconoCarpeta />
                <span className="recortar">{entrada.nombre}</span>
                <span className="texto-3">
                  {!entrada.accesible ? 'no accesible' : vigiladas.includes(entrada.ruta) ? 'ya vigilada' : ''}
                </span>
              </button>
            </li>
          ))}
      </ul>

      <p className="texto-2 parrafo">
        Dos carpetas vigiladas no pueden contenerse una a otra: el escaneo es recursivo y
        un mismo .srt no puede ser de las dos.
      </p>
      <button
        className="boton-primario boton-ancho"
        disabled={!listado || yaVigilada}
        onClick={() => listado && onElegir(listado.ruta)}
      >
        {yaVigilada ? 'Ya la vigilas' : listado ? `Vigilar ${nombreDeRuta(listado.ruta)}` : 'Elige una carpeta'}
      </button>
    </aside>
  )
}
