"""Constantes compartidas entre el actualizador y el instalador (installer/compresorfree.iss).

Un test (tests/test_instalador_iss.py) comprueba que el .iss usa exactamente estos
valores: si divergen no hay error visible, la app solo deja de reabrirse o de cerrarse.
"""

NOMBRE_EXE = "Compresorfree.exe"
CLAVE_REGISTRO = r"Software\Compresorfree"

FLAGS_INSTALADOR = ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                    "/CURRENTUSER", "/REABRIR=1")


def flags_instalador(ruta_sinal):
    """Argumentos del instalador para una actualizacion silenciosa que reabre la app."""
    return [*FLAGS_INSTALADOR, f"/SINAL={ruta_sinal}"]
