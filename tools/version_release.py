"""Decide la version de una release y si es una pre-release.

Esto es un script y no unas lineas de shell en el YAML porque la logica en YAML no
tiene pruebas, y aqui un error es silencioso: marcar como normal una pre-release hace
que `/releases/latest` la ofrezca como actualizacion a todos los usuarios.

Uso (en el workflow, con todo por variables de entorno, nunca interpolado en `run`):

    python3 tools/version_release.py --evento push --ref "$NOMBRE_REF"
    python3 tools/version_release.py --evento workflow_dispatch \\
        --entrada-version 1.3.0 --entrada-prerelease false

Escribe en $GITHUB_OUTPUT: version, numerica (sin sufijo, para Inno Setup), tag,
prerelease y publicar. Sin version pedida (push a main o dispatch vacio) solo se
compila: version=0.0.0-dev y publicar=false.
"""
import argparse
import os
import re
import sys

# Mismo SemVer estricto que verificacion.es_semver: sin ceros a la izquierda y solo ASCII.
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                     r"(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?")
VERSION_DEV = "0.0.0-dev"


def a_booleano(valor):
    """`inputs.prerelease` llega como TEXTO "true"/"false"; bool("false") seria True."""
    if isinstance(valor, bool):
        return valor
    return str(valor or "").strip().lower() in ("true", "1", "yes", "si")


def decidir(evento, ref="", entrada_version="", entrada_prerelease=False):
    """Devuelve {version, numerica, tag, prerelease, publicar}. SystemExit si no es valida."""
    if evento == "workflow_dispatch":
        pedida = entrada_version
        manual = True
    else:
        pedida = ref if ref.startswith("v") else ""
        manual = False
    if pedida == "":
        return {"version": VERSION_DEV, "numerica": "0.0.0", "tag": "v" + VERSION_DEV,
                "prerelease": False, "publicar": False}
    version = pedida[1:] if pedida.startswith("v") else pedida
    if not _SEMVER.fullmatch(version):
        sys.exit("Version no valida: debe ser vX.Y.Z o X.Y.Z, con sufijo opcional (-rc.1)")
    # En un tag decide el sufijo. Con el boton, manda la casilla: quien escribe 1.3.0-rc.1
    # y la desmarca quiere publicarla de verdad.
    prerelease = a_booleano(entrada_prerelease) if manual else "-" in version
    return {"version": version, "numerica": version.split("-")[0], "tag": "v" + version,
            "prerelease": prerelease, "publicar": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--evento", required=True, help="push | workflow_dispatch")
    ap.add_argument("--ref", default="", help="nombre del ref (tag) en un push")
    ap.add_argument("--entrada-version", default="", help="campo version del boton")
    ap.add_argument("--entrada-prerelease", default="", help="casilla prerelease del boton")
    args = ap.parse_args()
    d = decidir(args.evento, args.ref, args.entrada_version, args.entrada_prerelease)
    lineas = [f"version={d['version']}", f"numerica={d['numerica']}", f"tag={d['tag']}",
              f"prerelease={str(d['prerelease']).lower()}",
              f"publicar={str(d['publicar']).lower()}"]
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
