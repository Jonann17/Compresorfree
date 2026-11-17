"""Sube la firma opcional (manifest.json.minisig) de una release ya publicada.

    python herramientas/publicar_release.py --solo-firma vX.Y.Z [--repo Jonann17/Compresorfree]

La release la publica GitHub Actions. Si firmaste su manifest.json con minisign
(docs/GUIA_FIRMA.md), esto verifica la firma LOCALMENTE con las claves de
claves_confianza.py, comprueba que el manifest.json firmado es identico al publicado
y solo entonces sube release-vX.Y.Z/manifest.json.minisig. Si algo no cuadra, no sube
nada. Requiere el CLI de GitHub (gh) con la sesion iniciada.
"""

import argparse
import os
import tempfile

from _comun import REPO, carpeta_release, fallar, gh, leer_version, ver_release, verificacion

import claves_confianza  # noqa: E402  (la raiz del repo la anade _comun a sys.path)

MANIFIESTO = "manifest.json"
FIRMA = "manifest.json.minisig"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="version de la release, ej. v1.2.0")
    parser.add_argument("--solo-firma", action="store_true",
                        help="sube solo la firma (es el unico modo; se admite por claridad)")
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()
    version = leer_version(args.version)
    carpeta = carpeta_release(version)
    ruta_manifiesto = os.path.join(carpeta, MANIFIESTO)
    ruta_firma = os.path.join(carpeta, FIRMA)
    for ruta in (ruta_manifiesto, ruta_firma):
        if not os.path.isfile(ruta):
            fallar(f"falta {ruta}")

    with open(ruta_manifiesto, "rb") as f:
        datos = f.read()
    with open(ruta_firma, "rb") as f:
        firma = f.read()
    try:
        manifiesto = verificacion.verificar_manifiesto(datos, firma, claves_confianza.CLAVES)
    except verificacion.VerificacionFallida as e:
        motivo = str(e)
        if not claves_confianza.CLAVES:
            motivo += ". Anade antes tu clave publica a claves_confianza.py (docs/GUIA_FIRMA.md)"
        fallar(f"la firma del manifiesto no es valida: {motivo}. No se ha subido nada.")
    print("Firma del manifiesto valida.")
    if manifiesto["tipo"] != "release" or manifiesto["version"] != version:
        fallar(f"el manifiesto no es de la release v{version}")

    release = ver_release(version, args.repo)
    if release.get("isDraft"):
        fallar(f"v{version} es un borrador: no esta publicada.")
    with tempfile.TemporaryDirectory(prefix="compresorfree_firma_") as tmp:
        gh("release", "download", f"v{version}", "--repo", args.repo, "--dir", tmp,
           "--pattern", MANIFIESTO)
        with open(os.path.join(tmp, MANIFIESTO), "rb") as f:
            publicado = f.read()
    if publicado != datos:
        fallar("el manifest.json firmado no es identico al publicado en la release. "
               "No se ha subido nada.")

    print("Subiendo la firma...")
    gh("release", "upload", f"v{version}", "--repo", args.repo, "--clobber", ruta_firma)
    print(f"Firma de v{version} subida.")


if __name__ == "__main__":
    main()
