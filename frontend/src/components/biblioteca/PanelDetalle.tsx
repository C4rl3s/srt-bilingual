import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Candidato, Candidatos, EstadoCupo, Guia, MotivoDescarte, Trabajo } from '../../types'
import type { Obra } from '../../utils/biblioteca'
import { cabe, nombreProveedor, repartir } from '../../utils/cupos'
import { caracteres, numero, porcentaje } from '../../utils/formato'
import { IconoCerrar, IconoInfo } from '../Iconos'

interface Props {
  obra: Obra
  /** Trabajo en marcha de esta obra, si lo hay. */
  trabajo: Trabajo | undefined
  cupos: EstadoCupo[]
  /** `proveedor`: el elegido para traducir esta obra; sin él, lo elige el backend por cupo. */
  onGenerar: (subtituloId: number, forzarTraduccion: boolean, proveedor?: string) => Promise<void>
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
  // Proveedor elegido a mano para traducir esta obra; `null` = automático, por cupo.
  const [proveedorElegido, setProveedorElegido] = useState<string | null>(null)

  // Al cambiar de obra se olvida lo elegido a mano en la anterior (origen y
  // proveedor). Ajustar el estado durante el render (y no en un efecto) es lo que
  // recomienda React: evita pintar un fotograma con los datos de la obra de antes.
  const [rutaAnterior, setRutaAnterior] = useState(nodo.ruta)
  if (rutaAnterior !== nodo.ruta) {
    setRutaAnterior(nodo.ruta)
    setOrigenElegido(null)
    setProveedorElegido(null)
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
      await onGenerar(origen, forzar, proveedorElegido ?? undefined)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  // Previsión: el backend decide al crear el trabajo (ver `utils/cupos.ts`).
  const [proveedorPrevisto] = repartir(cupos, [
    { caracteres: nodo.num_caracteres, conGuia: nodo.ruta_guia !== null },
  ])
  const porId = (id: number | null) => candidatos?.candidatos.find((c) => c.subtitulo_id === id)
  const origen = porId(candidatos?.origen_id ?? null)
  const coreano = porId(candidatos?.coreano_id ?? null)
  // Se va a traducir (y no a fusionar): no hay coreano, o lo hay pero no casa.
  const vaATraducir = Boolean(origen) && (!coreano || candidatos?.fusion_aceptable === false)
  // Si el elegido a mano deja de caber (el cupo cambia al generar otras obras), se
  // vuelve a automático en vez de enviar una petición que el backend rechazaría.
  const elegidoCabe =
    proveedorElegido === null ||
    cupos.some((c) => c.proveedor === proveedorElegido && cabe(c, nodo.num_caracteres))
  const proveedor = elegidoCabe ? (proveedorElegido ?? proveedorPrevisto) : proveedorPrevisto

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
                  proveedor === null
                    ? 'Sin cupo suficiente en ningún proveedor'
                    : `Se traducirá con ${nombreProveedor(proveedor)}${
                        origenElegido === null
                          ? ` · ${caracteres(nodo.num_caracteres, nodo.caracteres_exactos)} caracteres`
                          : ''
                      }`
                }
              />
            ))}

          {vaATraducir && candidatos.guia && (
            <FilaGuia
              guia={candidatos.guia}
              proveedor={cupos.find((c) => c.proveedor === proveedor) ?? null}
              origenIngles={origen?.idioma === 'EN'}
            />
          )}

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

          {vaATraducir && cupos.length > 1 && (
            <ElegirProveedor
              cupos={cupos}
              caracteres={nodo.num_caracteres}
              previsto={proveedorPrevisto}
              elegido={elegidoCabe ? proveedorElegido : null}
              onElegir={setProveedorElegido}
            />
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

/**
 * La guía de traducción de la serie (glosario e instrucciones) y si se va a usar:
 * solo DeepL la aprovecha, y su glosario es de español a coreano.
 */
function FilaGuia({
  guia,
  proveedor,
  origenIngles,
}: {
  guia: Guia
  /** El proveedor que traducirá (elegido o previsto), o `null` si ninguno cabe. */
  proveedor: EstadoCupo | null
  origenIngles: boolean
}) {
  if (guia.error) {
    return (
      <p className="aviso aviso--error" title={guia.ruta}>
        La guía de traducción tiene un problema y no se podrá traducir hasta arreglarla:{' '}
        {guia.error}
      </p>
    )
  }
  const partes = [
    guia.terminos > 0 && `${numero(guia.terminos)} ${guia.terminos === 1 ? 'término' : 'términos'}`,
    guia.instrucciones > 0 &&
      `${guia.instrucciones} ${guia.instrucciones === 1 ? 'instrucción' : 'instrucciones'}`,
  ].filter(Boolean)
  // Qué pasará con ella al traducir: el proveedor puede ignorarla entera, o solo el
  // glosario si el origen es inglés.
  const aviso =
    proveedor && !proveedor.admite_guia
      ? `${nombreProveedor(proveedor.proveedor)} no admite glosario: se traducirá sin la guía`
      : origenIngles && guia.terminos > 0
        ? 'El glosario es de español a coreano: con origen inglés solo se aplican las instrucciones'
        : null

  return (
    <div className="fila-pista">
      <span className="fila-pista-barra fila-pista-barra--guia" aria-hidden="true" />
      <div className="fila-pista-texto">
        <div className="texto-2">Guía de traducción · {guia.carpeta}</div>
        <div className="recortar" title={guia.ruta}>
          {partes.join(' · ')}
        </div>
        {aviso && <div className="texto-3">{aviso}</div>}
      </div>
    </div>
  )
}

/**
 * Con qué proveedor traducir esta obra: automático (el backend elige por cupo, en el
 * orden de `TRANSLATION_PROVIDERS`) o uno concreto. Los que no pueden (sin clave, o
 * sin cupo para esta obra) salen desactivados y dicen por qué al pasar el ratón.
 */
function ElegirProveedor({
  cupos,
  caracteres,
  previsto,
  elegido,
  onElegir,
}: {
  cupos: EstadoCupo[]
  caracteres: number
  previsto: string | null
  elegido: string | null
  onElegir: (proveedor: string | null) => void
}) {
  return (
    <div className="elegir-proveedor">
      <div className="texto-2">Traducir con</div>
      <div className="filtros" role="radiogroup" aria-label="Proveedor de traducción">
        <button
          role="radio"
          aria-checked={elegido === null}
          className={`chip ${elegido === null ? 'chip--activo' : ''}`}
          onClick={() => onElegir(null)}
          title="La app elige el primero de tu lista de preferencia con cupo suficiente"
        >
          Automático
          {previsto && <span className="chip-cuenta">{nombreProveedor(previsto)}</span>}
        </button>
        {cupos.map((cupo) => {
          const puede = cabe(cupo, caracteres)
          const motivo = !cupo.disponible
            ? `No disponible: ${cupo.motivo}`
            : puede
              ? undefined
              : `Sin cupo suficiente: ${numero(cupo.libre ?? 0)} libres`
          return (
            <button
              key={cupo.proveedor}
              role="radio"
              aria-checked={elegido === cupo.proveedor}
              className={`chip ${elegido === cupo.proveedor ? 'chip--activo' : ''}`}
              disabled={!puede}
              title={motivo}
              onClick={() => onElegir(cupo.proveedor)}
            >
              {nombreProveedor(cupo.proveedor)}
              <span className="chip-cuenta">
                {!cupo.disponible ? 'sin clave' : cupo.libre === null ? '¿?' : `${abreviar(cupo.libre)} libres`}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** 1.977.147 → «1,98 M»; 999.939 → «999,9 mil»: caben en un chip. */
function abreviar(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2).replace('.', ',')} M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')} mil`
  return numero(n)
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
