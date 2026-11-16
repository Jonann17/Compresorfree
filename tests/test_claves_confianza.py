"""La configuracion REAL de claves_confianza.CLAVES es valida (hoy esta vacia: la prueba
pasa y empieza a proteger en cuanto el propietario anada sus claves)."""
import pytest

import claves_confianza
import verificacion
from firma_util import Par
from verificacion import VerificacionFallida


def comprobar_configuracion(claves):
    """Lanza AssertionError si `claves` no es una configuracion de confianza sana."""
    assert isinstance(claves, list)
    ids = []
    for clave in claves:
        # Misma validacion que se aplica a las claves de una rotacion firmada.
        try:
            verificacion._validar_clave(clave)
        except VerificacionFallida as e:
            raise AssertionError(f"clave invalida {clave!r}: {e}") from None
        ids.append(verificacion.normalizar_id(clave["id"]))
    assert len(ids) == len(set(ids)), "ids de clave repetidos"
    principales = [c for c in claves if c["rol"] == "principal"]
    assert len(principales) <= 1, "mas de una clave principal"


def test_la_configuracion_real_de_claves_es_valida():
    comprobar_configuracion(claves_confianza.CLAVES)


def test_cada_clave_real_verifica_una_firma_de_su_propio_id():
    # Solo comprueba formato/ids: sin la privada no se puede firmar. Las claves reales
    # deben ser legibles y su id coincidir con el de la clave publica.
    for clave in claves_confianza.CLAVES:
        id_publica, publica = verificacion.leer_clave_publica(clave["publica"])
        assert len(publica) == 32
        assert verificacion.normalizar_id(clave["id"]) == id_publica


# El validador de arriba no es decorativo: rechaza configuraciones rotas.
def _ok(rol="principal"):
    return Par().entrada(rol)


def test_comprobador_acepta_configuraciones_sanas():
    comprobar_configuracion([])
    comprobar_configuracion([_ok("principal")])
    comprobar_configuracion([_ok("principal"), _ok("respaldo")])
    comprobar_configuracion([_ok("respaldo"), _ok("respaldo")])


@pytest.mark.parametrize("mala", [
    lambda: [{**_ok(), "rol": "root"}],
    lambda: [{**_ok(), "id": Par().id}],                    # id de otra clave
    lambda: [{**_ok(), "publica": "AAAA"}],                 # clave publica rota
    lambda: [{"id": "AB", "rol": "principal"}],             # falta un campo
    lambda: [_ok("principal"), _ok("principal")],           # dos principales
    lambda: [{**_ok(), "extra": 1}],                        # campo desconocido
    lambda: [(lambda e: [e, dict(e, rol="respaldo")])(_ok())][0],   # id repetido
    lambda: "no es una lista",
])
def test_comprobador_rechaza_configuraciones_rotas(mala):
    with pytest.raises(AssertionError):
        comprobar_configuracion(mala())
