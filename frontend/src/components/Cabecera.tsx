import type { EstadoCupo, ProgresoSondeo, Trabajo } from '../types'
import { libreTotal, nombreProveedor } from '../utils/cupos'
import { numero, porcentaje, tituloDeRuta } from '../utils/formato'
import { IconoMenu } from './Iconos'

export type Seccion = 'biblioteca' | 'trabajos' | 'renombrado' | 'carpetas'

interface Props {
  seccion: Seccion
  onCambiar: (seccion: Seccion) => void
  trabajos: Trabajo[]
  cupos: EstadoCupo[]
  numPropuestas: number
  /** La lectura de pistas tras un escaneo, mientras dura; `null` si no hay ninguna. */
  sondeo: ProgresoSondeo | null
  /** Solo en pantallas estrechas: abre el árbol de carpetas como cajón. */
  onAbrirArbol: () => void
}

/** Barra superior: marca, pestañas, trabajo en curso, lectura de pistas y cupo libre total. */
export function Cabecera({
  seccion,
  onCambiar,
  trabajos,
  cupos,
  numPropuestas,
  sondeo,
  onAbrirArbol,
}: Props) {
  const activos = trabajos.filter((trabajo) => trabajo.activo)
  const libre = libreTotal(cupos)
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
            : enCurso.fase === 'EXTRAYENDO'
              ? 'extrayendo pistas'
              : `${enCurso.modo === 'FUSION' ? 'fusionando' : 'traduciendo'} ${porcentaje(enCurso)} %`}
        </button>
      )}

      {sondeo && (
        <button
          className="pildora"
          onClick={() => onCambiar('carpetas')}
          title="Tras escanear se leen las pistas de subtítulo de cada vídeo nuevo o cambiado"
        >
          <span className="punto punto--coreano" />
          Leyendo pistas
          {sondeo.total > 0 && ` · ${numero(sondeo.hechos)} de ${numero(sondeo.total)}`}
        </button>
      )}

      {libre !== null && (
        <button
          className="pildora"
          onClick={() => onCambiar('trabajos')}
          // El desglose por proveedor, al pasar el ratón; el detalle, en Trabajos.
          title={cupos
            .filter((c) => c.disponible)
            .map((c) => `${nombreProveedor(c.proveedor)}: ${c.libre === null ? '¿?' : numero(c.libre)} libres`)
            .join('\n')}
        >
          <span>Cupo</span>
          <b>{numero(libre)} libres</b>
        </button>
      )}
    </header>
  )
}
