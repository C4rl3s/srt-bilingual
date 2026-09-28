import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Candidato, Candidatos, EstadoCupo, MotivoDescarte, Trabajo } from '../../types'
import type { Obra } from '../../utils/biblioteca'
import { nombreProveedor, repartir } from '../../utils/cupos'
import { numero, porcentaje } from '../../utils/formato'
import { IconoCerrar, IconoInfo } from '../Iconos'

interface Props {
  obra: Obra
  /** Trabajo en marcha de esta obra, si lo hay. */
  trabajo: Trabajo | undefined
  cupos: EstadoCupo[]
  onGenerar: (subtituloId: number, forzarTraduccion: boolean) => Promise<void>
  onCerrar: () => void
}

const MOTIVOS: Record<MotivoDescarte, string> = {
  IDIOMA: 'otro idioma',
  FORZADO: 'forzado: solo carteles',
  POCOS_BLOQUES: 'demasiado corto: forzado encubierto',
  ERROR: 'no se puede leer',
}

const IDIOMAS: Record<string, string> = { ES: 'español', EN: 'inglés', KO: 'coreano' }

/**
 * Columna derecha: todo lo que hay que saber de una obra antes de generar su
 * bilingüe, y el botón para hacerlo.
 */
export function PanelDetalle({ obra, trabajo, cupos, onGenerar, onCerrar }: Props) {
  const { nodo } = obra
  const [candidatos, setCandidatos] = useState<Candidatos | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [origenElegido, setOrigenElegido] = useState<number | null>(null)
  const [cambiando, setCambiando] = useState(false)
  const [enviando, setEnviando] = useState(false)

  // Al cambiar de obra se olvida el origen elegido a mano en la anterior.
  // Ajustar el estado durante el render (y no en un efecto) es lo que recomienda
  // React: evita pintar un fotograma con los datos de la obra de antes.
  const [rutaAnterior, setRutaAnterior] = useState(nodo.ruta)
  if (rutaAnterior !== nodo.ruta) {
    setRutaAnterior(nodo.ruta)
    setOrigenElegido(null)
    setCambiando(false)
    setCandidatos(null)
    setError(null)
  }

  const idSubtitulo = nodo.subtitulo_ids[0]

  useEffect(() => {
    if (idSubtitulo === undefined) return
    // Si el usuario cambia de obra antes de que llegue la respuesta, la respuesta
    // vieja se descarta: si no, pintaría los candidatos de otra película.
    let vigente = true
    api
      .candidatos(idSubtitulo, origenElegido ?? undefined)
      .then((respuesta) => vigente && setCandidatos(respuesta))
      .catch((e: Error) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [idSubtitulo, origenElegido, nodo.estado_obra])

  async function generar(forzar: boolean) {
    const origen = candidatos?.origen_id
    if (!origen) return
    setEnviando(true)
    setError(null)
    try {
      await onGenerar(origen, forzar)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  // Previsión: el backend decide al crear el trabajo (ver `utils/cupos.ts`).
  const [proveedorPrevisto] = repartir(cupos, [nodo.num_caracteres])
  const porId = (id: number | null) => candidatos?.candidatos.find((c) => c.subtitulo_id === id)
  const origen = porId(candidatos?.origen_id ?? null)
  const coreano = porId(candidatos?.coreano_id ?? null)

  return (
    <aside className="detalle" aria-label="Detalle de la obra">
      <div className="detalle-cabecera">
        <div>
          <div className="texto-2 recortar">
            {obra.anio ? `${obra.anio} · ` : ''}
            {nodo.nombre}
          </div>
          <h2>{obra.titulo}</h2>
        </div>
        <button className="boton-icono detalle-cerrar" onClick={onCerrar} aria-label="Cerrar detalle">
          <IconoCerrar />
        </button>
      </div>

      {nodo.estado_obra === 'SIN_SUBTITULOS' && (
        <Nota titulo="Subtítulos dentro del vídeo">
          No hay ningún .srt junto a este vídeo: sus subtítulos van dentro del fichero. Se
          podrán usar cuando llegue el soporte MKV (Fase 5).
        </Nota>
      )}

      {error && <p className="aviso aviso--error">{error}</p>}
      {idSubtitulo !== undefined && !candidatos && !error && <p className="texto-2">Cargando…</p>}

      {candidatos && (
        <>
          {origen ? (
            <Pista
              tipo="origen"
              etiqueta={`Origen · ${IDIOMAS[origen.idioma] ?? origen.idioma}`}
              valor={`${origen.nombre} · ${numero(origen.num_bloques)} bloques`}
              accion={
                <button className="boton-pequeno" onClick={() => setCambiando(!cambiando)}>
                  {cambiando ? 'Listo' : 'Cambiar'}
                </button>
              }
            />
          ) : (
            <Nota titulo="Falta un subtítulo en español o inglés">
              Busca un .srt en español o en inglés, déjalo en la carpeta de la película y
              vuelve a escanear.
            </Nota>
          )}

          {(cambiando || !origen) && (
            <ListaCandidatos
              candidatos={candidatos.candidatos}
              elegido={candidatos.origen_id}
              onElegir={(id) => {
                setOrigenElegido(id)
                setCambiando(false)
              }}
            />
          )}

          {origen &&
            (coreano ? (
              <Pista
                tipo="coreano"
                etiqueta="Coreano · ya existe"
                valor={`${coreano.nombre} · ${numero(coreano.num_bloques)} bloques`}
              />
            ) : (
              <Pista
                tipo="falta"
                etiqueta="Coreano · no hay"
                valor={
                  proveedorPrevisto === null
                    ? 'Sin cupo suficiente en ningún proveedor'
                    : `Se traducirá con ${nombreProveedor(proveedorPrevisto)}${
                        origenElegido === null ? ` · ${numero(nodo.num_caracteres)} caracteres` : ''
                      }`
                }
              />
            ))}

          {candidatos.calidad_alineacion !== null && (
            <div className={`calidad ${candidatos.fusion_aceptable ? '' : 'calidad--mala'}`}>
              <div className="calidad-fila">
                <b>{candidatos.fusion_aceptable ? 'Fusión · casan bien' : 'Fusión · no casan'}</b>
                <span className="texto-2">
                  calidad {candidatos.calidad_alineacion.toFixed(2).replace('.', ',')}
                  {candidatos.fusion_aceptable ? ' · sin cupo' : ' · mínimo 0,70'}
                </span>
              </div>
              <div className="barra">
                <div
                  className="barra-relleno barra-relleno--coreano"
                  style={{ width: `${Math.round(candidatos.calidad_alineacion * 100)}%` }}
                />
              </div>
              {!candidatos.fusion_aceptable && (
                <p className="texto-2">
                  El coreano parece de otra versión de la película. Puedes traducirla en su
                  lugar; la app elegirá el proveedor según su cupo.
                </p>
              )}
            </div>
          )}

          {candidatos.muestra.length > 0 && (
            <div className="muestra-bloque">
              <div className="texto-2">Así se verá</div>
              <div className="muestra">
                {candidatos.muestra.map((m) => (
                  <div key={m.tiempo} className="muestra-cue">
                    <div className="muestra-tiempo">{m.tiempo}</div>
                    <div className="muestra-origen">{m.origen}</div>
                    <div className="muestra-coreano">{m.coreano ?? 'aquí irá la traducción al coreano'}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="detalle-pie">
        {trabajo ? (
          <div className="progreso">
            <div className="calidad-fila">
              <b>{trabajo.estado === 'QUEUED' ? 'En cola' : trabajo.modo === 'FUSION' ? 'Fusionando' : `Traduciendo con ${nombreProveedor(trabajo.proveedor)}`}</b>
              <span className="texto-2">{porcentaje(trabajo)} %</span>
            </div>
            <div className="barra">
              <div className="barra-relleno" style={{ width: `${porcentaje(trabajo)}%` }} />
            </div>
          </div>
        ) : nodo.estado_obra === 'DUAL' ? (
          <>
            <Nota titulo="Bilingüe listo">{nodo.ruta_bilingue}</Nota>
            <button className="boton-secundario boton-ancho" disabled={!origen || enviando} onClick={() => generar(false)}>
              Volver a generar
            </button>
          </>
        ) : origen ? (
          candidatos?.fusion_aceptable === false ? (
            <button className="boton-primario boton-ancho" disabled={enviando} onClick={() => generar(true)}>
              Traducir
            </button>
          ) : (
            <button className="boton-primario boton-ancho" disabled={enviando} onClick={() => generar(false)}>
              {enviando ? 'Enviando…' : 'Generar bilingüe'}
            </button>
          )
        ) : null}
      </div>
    </aside>
  )
}

function Pista({
  tipo,
  etiqueta,
  valor,
  accion,
}: {
  tipo: 'origen' | 'coreano' | 'falta'
  etiqueta: string
  valor: string
  accion?: ReactNode
}) {
  return (
    <div className={`fila-pista fila-pista--${tipo}`}>
      <span className={`fila-pista-barra fila-pista-barra--${tipo}`} aria-hidden="true" />
      <div className="fila-pista-texto">
        <div className="texto-2">{etiqueta}</div>
        <div className="recortar" title={valor}>
          {valor}
        </div>
      </div>
      {accion}
    </div>
  )
}

function ListaCandidatos({
  candidatos,
  elegido,
  onElegir,
}: {
  candidatos: Candidato[]
  elegido: number | null
  onElegir: (id: number) => void
}) {
  return (
    <ul className="candidatos">
      {candidatos.map((c) => {
        // Otro idioma o un fichero ilegible no pueden ser origen de ninguna manera;
        // un forzado o uno corto sí, si el usuario sabe que está completo.
        const posible = (c.idioma === 'ES' || c.idioma === 'EN') && c.descarte !== 'ERROR'
        return (
          <li key={c.subtitulo_id}>
            <button
              className={`candidato ${c.subtitulo_id === elegido ? 'candidato--elegido' : ''}`}
              disabled={!posible}
              onClick={() => onElegir(c.subtitulo_id)}
            >
              <span className="recortar">{c.nombre}</span>
              <span className="texto-3">
                {c.idioma === 'UNKNOWN' ? '¿?' : c.idioma} · {numero(c.num_bloques)}
                {c.descarte ? ` · ${MOTIVOS[c.descarte]}` : ''}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function Nota({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="nota-detalle">
      <IconoInfo />
      <div>
        <b>{titulo}</b>
        <p>{children}</p>
      </div>
    </div>
  )
}
