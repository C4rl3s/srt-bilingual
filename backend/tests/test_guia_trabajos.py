"""Tests de la guía de traducción en el resto de la app: índice del escaneo, árbol,
elección de proveedor y trabajos (hito 3 de `docs/plans/plan-glosario-por-obra.md`)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.library_folder import CarpetaBiblioteca
from app.models.translation_job import TrabajoTraduccion
from app.services import trabajos
from app.services.library_tree import construir_arbol
from app.services.scanner import escanear
from app.services.translation import consumo
from app.services.translation.consumo import EstadoCupo, FuenteCupo
from app.services.translation.eleccion import Asignador
from app.services.translation.guia import NOMBRE_FICHERO
from tests.conftest import TraductorFalso, escribir_srt, escribir_video, srt_completo

Registrar = Callable[..., list[CarpetaBiblioteca]]

GUIA = '[glosario]\n"Marley" = "마레"\n\n[instrucciones]\nlista = ["Usa 반말 entre amigos."]\n'


def _serie(raiz: Path, guia: str | None = GUIA) -> Path:
    """`raiz/Serie/S1/Capitulo.mkv` con su `.es.srt`, y la guía en `raiz/Serie`."""
    temporada = raiz / "Serie" / "S1"
    escribir_video(temporada / "Capitulo.mkv")
    escribir_srt(temporada / "Capitulo.es.srt", srt_completo())
    if guia is not None:
        (raiz / "Serie" / NOMBRE_FICHERO).write_text(guia, encoding="utf-8")
    return temporada


def _hojas(nodos) -> list:
    return [h for n in nodos for h in ([n] if n.hoja else _hojas(n.hijos))]


def _estado(proveedor: str, admite_guia: bool, libre: int | None = None) -> EstadoCupo:
    return EstadoCupo(proveedor, True, None, FuenteCupo.REGISTRO, 0, 0, libre, admite_guia)


def _dos_proveedores() -> list[EstadoCupo]:
    # Azure primero en la preferencia, como en el `.env` real; solo DeepL admite guía.
    return [_estado("azure", False), _estado("deepl", True)]


class TraductorSinGuia(TraductorFalso):
    nombre = "azure"
    admite_guia = False


def _origen(db: Session, carpeta: CarpetaBiblioteca):
    return next(s for s in carpeta.subtitulos if s.nombre == "Capitulo.es.srt")


def _ejecutar(engine: Engine, trabajo: TrabajoTraduccion, traductor: TraductorFalso) -> None:
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    trabajos.ejecutar(trabajo.id, fabrica, lambda _nombre: traductor)


# --- Índice del escaneo ---


def test_el_escaneo_indexa_las_guias(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)

    resumen = escanear(db)

    assert resumen.guias == 1
    assert [g.ruta for g in carpeta.guias] == [str(tmp_path / "Serie" / NOMBRE_FICHERO)]
    assert resumen.total == 1  # la guía no cuenta como subtítulo


def test_una_guia_borrada_sale_del_indice(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    (tmp_path / "Serie" / NOMBRE_FICHERO).unlink()
    escanear(db)
    db.refresh(carpeta)

    assert carpeta.guias == []


def test_reescanear_no_duplica_la_guia(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)

    escanear(db)
    escanear(db)

    assert len(carpeta.guias) == 1


def test_solo_cuenta_el_nombre_exacto(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    # En el NAS (Linux) leer el fichero distingue mayúsculas: otro nombre no es guía.
    _serie(tmp_path, guia=None)
    (tmp_path / "Serie" / "notas.toml").write_text(GUIA, encoding="utf-8")
    (carpeta,) = registrar_carpetas(tmp_path)

    escanear(db)

    assert carpeta.guias == []


# --- Árbol ---


def test_el_arbol_dice_que_guia_le_toca_a_cada_obra(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    escribir_video(tmp_path / "Otra" / "Pelicula.mkv")
    registrar_carpetas(tmp_path)
    escanear(db)

    hojas = {h.nombre: h for h in _hojas(construir_arbol(db))}

    assert hojas["Capitulo"].ruta_guia == str(tmp_path / "Serie" / NOMBRE_FICHERO)
    assert hojas["Pelicula"].ruta_guia is None


def test_el_arbol_no_mira_el_disco(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Una guía creada después del escaneo aparece al volver a escanear, no antes."""
    _serie(tmp_path, guia=None)
    registrar_carpetas(tmp_path)
    escanear(db)
    (tmp_path / "Serie" / NOMBRE_FICHERO).write_text(GUIA, encoding="utf-8")

    (hoja,) = _hojas(construir_arbol(db))

    assert hoja.ruta_guia is None


# --- Elección de proveedor ---


def test_con_guia_se_prefiere_el_proveedor_que_la_admite() -> None:
    asignador = Asignador(_dos_proveedores())

    assert asignador.asignar(10_000) == "azure"
    assert asignador.asignar(10_000, con_guia=True) == "deepl"


def test_con_guia_si_no_cabe_en_ninguno_que_la_admita_va_a_otro() -> None:
    asignador = Asignador([_estado("azure", False), _estado("deepl", True, libre=100)])

    assert asignador.asignar(10_000, con_guia=True) == "azure"


def test_con_guia_se_respeta_el_orden_dentro_de_cada_grupo() -> None:
    asignador = Asignador(
        [_estado("a", False), _estado("b", True), _estado("c", False), _estado("d", True)]
    )

    assert asignador.asignar(1, con_guia=True) == "b"


def test_el_proveedor_elegido_a_mano_manda_aunque_haya_guia() -> None:
    asignador = Asignador(_dos_proveedores())

    assert asignador.asignar(10_000, solo="azure", con_guia=True) == "azure"


def test_el_cupo_dice_si_el_proveedor_admite_la_guia(db: Session) -> None:
    fabricas = {"deepl": TraductorFalso, "azure": TraductorSinGuia}

    estados = consumo.estados(db, ["deepl", "azure"], lambda n: fabricas[n](), lambda _n: None)

    assert [(e.proveedor, e.admite_guia) for e in estados] == [("deepl", True), ("azure", False)]


# --- Trabajos ---


def test_crear_con_guia_elige_el_proveedor_que_la_admite(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    (trabajo,), rechazos = trabajos.crear(
        db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores
    )

    assert rechazos == []
    assert trabajo.proveedor == "deepl"


def test_crear_sin_guia_sigue_la_preferencia_configurada(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia=None)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)

    assert trabajo.proveedor == "azure"


def test_crear_con_una_guia_rota_la_rechaza_con_el_motivo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia="[glosario\n")
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    creados, (rechazo,) = trabajos.crear(
        db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores
    )

    assert creados == []
    assert NOMBRE_FICHERO in rechazo.motivo and "TOML" in rechazo.motivo


def test_el_trabajo_usa_la_guia_y_la_anota(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)
    db.refresh(trabajo)

    assert trabajo.mensaje_error is None
    guia = traductor.guias[0]
    assert guia.glosario == {"Marley": "마레"}
    assert all(g is guia for g in traductor.guias)  # la misma en cada paso
    assert trabajo.guia == f"{tmp_path / 'Serie' / NOMBRE_FICHERO} ({guia.huella})"


def test_la_guia_se_relee_al_ejecutar(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Editarla mientras el trabajo espera en cola cuenta: el disco manda."""
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    (tmp_path / "Serie" / NOMBRE_FICHERO).write_text(
        '[glosario]\n"Marley" = "마레"\n"Paradis" = "파라디"\n', encoding="utf-8"
    )
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)

    assert traductor.guias[0].glosario["Paradis"] == "파라디"


def test_con_contexto_cada_bloque_lleva_sus_vecinos_aunque_cambie_de_lote(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia=GUIA + "\n[opciones]\ncontexto = true\n")
    temporada = tmp_path / "Serie" / "S1"
    # Bloques numerados para ver qué vecinos le tocan a cada uno.
    srt = "\n".join(
        f"{i + 1}\n00:{i // 30:02d}:{i % 30 * 2:02d},000 --> 00:{i // 30:02d}:{i % 30 * 2:02d},900"
        f"\nfrase {i}\n"
        for i in range(120)
    )
    escribir_srt(temporada / "Capitulo.es.srt", srt)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)

    primer_lote, segundo_lote, _ = traductor.contextos
    assert primer_lote[0] == "frase 1 frase 2"  # el primero no tiene anteriores
    # El último del primer lote (49) ve los dos primeros del segundo (50 y 51).
    assert primer_lote[49] == "frase 47 frase 48 frase 50 frase 51"
    assert segundo_lote[0] == "frase 48 frase 49 frase 51 frase 52"


def test_sin_la_opcion_no_hay_contexto(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)

    assert set(traductor.contextos) == {None}


def test_un_proveedor_sin_guia_no_la_anota(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(
        db, [_origen(db, carpeta).id], proveedor="azure", estados_cupo=_dos_proveedores
    )

    _ejecutar(engine, trabajo, TraductorSinGuia())
    db.refresh(trabajo)

    assert trabajo.mensaje_error is None
    assert trabajo.guia is None


def test_sin_guia_el_trabajo_no_anota_nada(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia=None)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)
    db.refresh(trabajo)

    assert trabajo.guia is None
    assert set(traductor.guias) == {None}


def _guia_del_panel(client: TestClient, db: Session, carpeta: CarpetaBiblioteca) -> dict | None:
    respuesta = client.get(f"/subtitles/{_origen(db, carpeta).id}/candidatos")
    assert respuesta.status_code == 200
    return respuesta.json()["guia"]


def test_el_panel_resume_la_guia(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    guia = _guia_del_panel(client, db, carpeta)

    assert guia == {
        "ruta": str(tmp_path / "Serie" / NOMBRE_FICHERO),
        "carpeta": "Serie",
        "terminos": 1,
        "instrucciones": 1,
        "error": None,
    }


def test_el_panel_sin_guia(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia=None)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    assert _guia_del_panel(client, db, carpeta) is None


def test_el_panel_explica_una_guia_rota(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path, guia="[glosario\n")
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)

    guia = _guia_del_panel(client, db, carpeta)

    assert "TOML" in guia["error"]


def test_el_panel_avisa_si_la_guia_se_borro_tras_escanear(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (tmp_path / "Serie" / NOMBRE_FICHERO).unlink()

    guia = _guia_del_panel(client, db, carpeta)

    assert "vuelve a escanear" in guia["error"]


def test_una_guia_rota_al_ejecutar_falla_el_trabajo_con_el_motivo(
    db: Session, engine: Engine, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie(tmp_path)
    (carpeta,) = registrar_carpetas(tmp_path)
    escanear(db)
    (trabajo,), _ = trabajos.crear(db, [_origen(db, carpeta).id], estados_cupo=_dos_proveedores)
    (tmp_path / "Serie" / NOMBRE_FICHERO).write_text("[glosario\n", encoding="utf-8")
    traductor = TraductorFalso()

    _ejecutar(engine, trabajo, traductor)
    db.refresh(trabajo)

    assert trabajo.estado.value == "FAILED"
    assert NOMBRE_FICHERO in trabajo.mensaje_error
    assert traductor.llamadas == []  # no se traduce sin ella
