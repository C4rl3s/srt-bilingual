import type { Cupo, Trabajo } from '../types'
import { numero, porcentaje, tituloDeRuta } from '../utils/formato'
import { IconoMenu } from './Iconos'

export type Seccion = 'biblioteca' | 'trabajos' | 'renombrado' | 'carpetas'

interface Props {
  seccion: Seccion
  onCambiar: (seccion: Seccion) => void
  trabajos: Trabajo[]
  cupo: Cupo | null
  numPropuestas: number
  /** Solo en pantallas estrechas: abre el árbol de carpetas como cajón. */
  onAbrirArbol: () => void
}

/** Barra superior: marca, pestañas, trabajo en curso y cupo del proveedor. */
export function Cabecera({ seccion, onCambiar, trabajos, cupo, numPropuestas, onAbrirArbol }: Props) {
  const activos = trabajos.filter((trabajo) => trabajo.activo)
  // El que más avanzado va es el que se enseña en la píldora.
  const enCurso = activos.find((trabajo) => trabajo.estado === 'RUNNING') ?? activos[0]

  const pestanas: { clave: Seccion; texto: string; cuenta?: number }[] = [
    { clave: 'biblioteca', texto: 'Biblioteca' },
    { clave: 'trabajos', texto: 'Trabajos', cuenta: activos.length },
    { clave: 'renombrado', texto: 'Renombrar para Plex', cuenta: numPropuestas },
  ]
  // Carpetas cuelga de la biblioteca: con ella abierta, la pestaña marcada sigue
  // siendo «Biblioteca».
  const marcada = seccion === 'carpetas' ? 'biblioteca' : seccion

  return (
    <header className="cabecera">
      <button className="cabecera-menu boton-icono" onClick={onAbrirArbol} aria-label="Abrir carpetas">
        <IconoMenu />
      </button>

      <div className="marca" aria-label="srt-bilingual">
        <span className="marca-pistas" aria-hidden="true">
          <span className="marca-pista marca-pista--origen" />
          <span className="marca-pista marca-pista--coreano" />
        </span>
        <span className="marca-texto">dos pistas</span>
      </div>

      <nav className="pestanas" aria-label="Secciones">
        {pestanas.map((pestana) => (
          <button
            key={pestana.clave}
            className={`pestana ${marcada === pestana.clave ? 'pestana--activa' : ''}`}
            aria-current={marcada === pestana.clave ? 'page' : undefined}
            onClick={() => onCambiar(pestana.clave)}
          >
            {pestana.texto}
            {pestana.cuenta ? <span className="pestana-cuenta">{pestana.cuenta}</span> : null}
          </button>
        ))}
      </nav>

      <div className="cabecera-hueco" />

      {enCurso && (
        <button className="pildora" onClick={() => onCambiar('trabajos')}>
          <span className="punto punto--origen" />
          {tituloDeRuta(enCurso.ruta_origen)} ·{' '}
          {enCurso.estado === 'QUEUED'
            ? 'en cola'
            : `${enCurso.modo === 'FUSION' ? 'fusionando' : 'traduciendo'} ${porcentaje(enCurso)} %`}
        </button>
      )}

      {cupo && cupo.limite !== null && (
        <div className="pildora pildora--cupo" title={`${numero(cupo.usados)} usados de ${numero(cupo.limite)}`}>
          <span>{cupo.proveedor === 'deepl' ? 'DeepL' : cupo.proveedor}</span>
          <b>{numero(cupo.limite - cupo.usados)} libres</b>
        </div>
      )}
    </header>
  )
}
