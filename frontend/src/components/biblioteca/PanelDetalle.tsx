import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Candidato, Candidatos, EstadoCupo, MotivoDescarte, Trabajo } from '../../types'
import type { Obra } from '../../utils/biblioteca'
import { nombreProveedor, repartir } from '../../utils/cupos'
import { caracteres, numero, porcentaje } from '../../utils/formato'
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
  IMAGEN: 'solo en imagen: sin texto que leer',
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
  // Se incrementa para volver a pedir los candidatos sin cambiar nada más: mientras
  // se extraen las pistas del vídeo, y justo después.
  const [recarga, setRecarga] = useState(0)

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
  }, [idSubtitulo, origenElegido, nodo.estado_obra, recarga])

  // Mientras el backend extrae las pistas, se pregunta cada pocos segundos: cuando
  // acaba, los candidatos traen ya la muestra y la calidad de la fusión.
  const extrayendo = candidatos?.extrayendo ?? false
  useEffect(() => {
    if (!extrayendo) return
    const temporizador = setInterval(() => setRecarga((n) => n + 1), 3000)
    return () => clearInterval(temporizador)
  }, [extrayendo])

  async function extraer() {
    if (!candidatos?.video_id) return
    setError(null)
    try {
      const respuesta = await api.extraerPistas(candidatos.video_id)
      if (respuesta.en_curso) {
        setCandidatos({ ...candidatos, extrayendo: true, error_extraccion: null })
      } else {
        setRecarga((n) => n + 1) // ya estaban extraídas: basta con volver a pedir
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

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
        <Nota titulo="Sin subtítulos">
          Ni hay un .srt junto a este vídeo ni trae pistas de texto dentro. Si acabas de
          escanear, puede que aún se estén leyendo sus pistas: espera a que termine.
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
              valor={`${origen.nombre} · ${bloques(origen)}`}
              enVideo={origen.es_pista}
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
                valor={`${coreano.nombre} · ${bloques(coreano)}`}
                enVideo={coreano.es_pista}
              />
            ) : (
              <Pista
                tipo="falta"
                etiqueta="Coreano · no hay"
                valor={
                  proveedorPrevisto === null
                    ? 'Sin cupo suficiente en ningún proveedor'
                    : `Se traducirá con ${nombreProveedor(proveedorPrevisto)}${
                        origenElegido === null
                          ? ` · ${caracteres(nodo.num_caracteres, nodo.caracteres_exactos)} caracteres`
                          : ''
                      }`
                }
              />
            ))}

          {candidatos.extraccion_pendiente && (
            <div className="calidad">
              <div className="calidad-fila">
                <b>Pistas dentro del vídeo</b>
                <span className="texto-2">sin extraer</span>
              </div>
              <p className="texto-2">
                Para ver cómo quedará{coreano ? ' y si la fusión casa' : ''} hay que sacar las
                pistas del vídeo, y eso obliga a leer el fichero entero: 1–2 min por episodio.
                Si generas directamente, se extraen al empezar.
              </p>
              {candidatos.error_extraccion && (
                <p className="aviso aviso--error">{candidatos.error_extraccion}</p>
              )}
              {extrayendo ? (
                <div className="barra barra--indeterminada" aria-label="Extrayendo pistas">
                  <div className="barra-relleno barra-relleno--coreano" />
                </div>
              ) : (
                <button className="boton-secundario boton-ancho" onClick={extraer}>
                  Extraer pistas
                </button>
              )}
            </div>
          )}

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
              <b>
                {trabajo.estado === 'QUEUED'
                  ? 'En cola'
                  : trabajo.fase === 'EXTRAYENDO'
                    ? 'Extrayendo las pistas del vídeo'
                    : trabajo.modo === 'FUSION'
                      ? 'Fusionando'
                      : `Traduciendo con ${nombreProveedor(trabajo.proveedor)}`}
              </b>
              {trabajo.fase !== 'EXTRAYENDO' && <span className="texto-2">{porcentaje(trabajo)} %</span>}
            </div>
            <div className={`barra ${trabajo.fase === 'EXTRAYENDO' ? 'barra--indeterminada' : ''}`}>
              <div
                className="barra-relleno"
                style={trabajo.fase === 'EXTRAYENDO' ? undefined : { width: `${porcentaje(trabajo)}%` }}
              />
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

/**
 * Las líneas de un subtítulo, dichas con su precisión: exactas en un `.srt` o en una
 * pista ya extraída; «≈» con las de la cabecera de una pista (cuentan carteles y
 * karaoke); «por saber» si la pista no trae estadísticas.
 */
function bloques(c: Candidato): string {
  if (c.metricas_exactas) return `${numero(c.num_bloques)} líneas`
  if (c.num_bloques === 0) return 'líneas por saber'
  return `≈ ${numero(c.num_bloques)} líneas`
}

function Pista({
  tipo,
  etiqueta,
  valor,
  enVideo = false,
  accion,
}: {
  tipo: 'origen' | 'coreano' | 'falta'
  etiqueta: string
  valor: string
  /** Es una pista incrustada en el vídeo, no un `.srt`. */
  enVideo?: boolean
  accion?: ReactNode
}) {
  return (
    <div className={`fila-pista fila-pista--${tipo}`}>
      <span className={`fila-pista-barra fila-pista-barra--${tipo}`} aria-hidden="true" />
      <div className="fila-pista-texto">
        <div className="texto-2">
          {etiqueta}
          {enVideo && <span className="etiqueta-video">dentro del vídeo</span>}
        </div>
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
              <span className="recortar">
                {c.nombre}
                {c.es_pista && <span className="etiqueta-video">vídeo</span>}
              </span>
              <span className="texto-3">
                {c.idioma === 'UNKNOWN' ? '¿?' : c.idioma} · {bloques(c)}
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
