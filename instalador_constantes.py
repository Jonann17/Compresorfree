"""Constantes compartidas entre el actualizador y el instalador (installer/compresorfree.iss)."""

NOMBRE_EXE = "Compresorfree.exe"
CLAVE_REGISTRO = r"Software\Compresorfree"


def flags_instalador(ruta_sinal):
    """Argumentos del instalador Inno Setup para una actualizacion silenciosa."""
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
            "/CURRENTUSER", "/REABRIR=1", f"/SINAL={ruta_sinal}"]
