"""installer/compresorfree.iss: comprobaciones de contenido (aqui no se ejecuta Inno Setup).

Que pasen no prueba que el instalador COMPILE; solo que respeta el contrato con la app."""
import os
import re
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import instalador_constantes as ic  # noqa: E402

with open(os.path.join(RAIZ, "installer", "compresorfree.iss"), encoding="utf-8") as _f:
    ISS = _f.read()
SIN_COMENTARIOS = "\n".join(l for l in ISS.splitlines() if not l.lstrip().startswith(("//", ";")))


def test_flags_del_actualizador_coinciden_con_el_iss():
    flags = ic.flags_instalador(r"C:\tmp\sinal")
    nombres = {f.split("=")[0] for f in flags}
    assert {"/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/CURRENTUSER",
            "/REABRIR", "/SINAL"} <= nombres
    assert flags[-1].startswith("/SINAL=") and "/REABRIR=1" in flags
    # Los dos parametros propios del instalador se leen con {param:...} y el mismo nombre.
    assert "{param:REABRIR|0}" in SIN_COMENTARIOS and "'1'" in SIN_COMENTARIOS
    assert "{param:SINAL|" in SIN_COMENTARIOS
    assert "/REABRIR" in ISS and "/SINAL" in ISS


def test_nombre_del_exe_y_del_instalador():
    assert ic.NOMBRE_EXE == "Compresorfree.exe"
    assert '#define AppExe "Compresorfree.exe"' in ISS
    assert "OutputBaseFilename=Compresorfree-Setup-{#MyAppVersion}" in ISS


def test_clave_de_registro_hkcu():
    assert ic.CLAVE_REGISTRO == r"Software\Compresorfree"
    lineas = [l for l in SIN_COMENTARIOS.splitlines() if l.startswith("Root:")]
    assert lineas and all(l.startswith("Root: HKCU;") for l in lineas)
    for valor in ("InstallPath", "Version"):
        assert any(f'Subkey: "{ic.CLAVE_REGISTRO}"' in l and f'ValueName: "{valor}"' in l
                   for l in lineas), valor


def test_instalacion_por_usuario_sin_administrador():
    assert "PrivilegesRequired=lowest" in SIN_COMENTARIOS
    assert "PrivilegesRequiredOverridesAllowed=commandline" in SIN_COMENTARIOS
    assert r"DefaultDirName={localappdata}\Programs\Compresorfree" in SIN_COMENTARIOS
    assert "CloseApplications=force" in SIN_COMENTARIOS
    assert "HKLM" not in SIN_COMENTARIOS


def test_appid_es_un_guid_fijo():
    m = re.search(r"^AppId=\{\{([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})\}",
                  ISS, re.M)
    assert m, "AppId debe ser un GUID fijo (con la llave doble de Inno)"


def test_run_reabre_solo_con_el_flag_y_la_normal_es_postinstall():
    runs = ISS.split("[Run]")[1].split("[UninstallDelete]")[0]
    lineas = [l for l in runs.splitlines() if l.startswith("Filename:")]
    assert len(lineas) == 2
    normal = next(l for l in lineas if "postinstall" in l)
    assert "skipifsilent" in normal and "Check:" not in normal
    reabrir = next(l for l in lineas if "postinstall" not in l)
    assert "runasoriginaluser" in reabrir and "Check: Reabrir" in reabrir
    assert re.search(r"function Reabrir: Boolean;", ISS)


def test_la_senal_se_crea_al_arrancar():
    cuerpo = ISS.split("function InitializeSetup")[1]
    assert "SaveStringToFile(Sinal" in cuerpo and "Result := True" in cuerpo


def test_instala_desde_dist_y_la_version_sin_sufijo_para_inno():
    assert r'Source: "..\dist\Compresorfree\*"' in ISS
    assert "VersionInfoVersion={#MyVersionInfo}" in ISS
    assert '"-"' in ISS  # recorta el sufijo de pre-release si no se pasa /DMyVersionInfo


def test_el_workflow_compila_el_iss_con_ese_nombre():
    with open(os.path.join(RAIZ, ".github", "workflows", "compilar.yml"), encoding="utf-8") as f:
        wf = f.read()
    assert "installer/compresorfree.iss" in wf and "Compresorfree-Setup-" in wf
    assert "choco install innosetup -y" in wf


@pytest.mark.parametrize("dato", ["{{", "[Setup]", "[Run]", "[Registry]", "[Code]"])
def test_secciones_basicas(dato):
    assert dato in ISS
