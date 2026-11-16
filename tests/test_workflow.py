"""PR3-A: endurecimiento del workflow de releases (garantia 7)."""
import glob
import os
import re

import pytest
import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA = os.path.join(RAIZ, ".github", "workflows", "compilar.yml")

HEREDADOS = ["Compresorfree-Windows.zip", "Compresorfree-macOS-AppleSilicon.dmg",
             "Compresorfree-macOS-Intel.dmg"]


@pytest.fixture(scope="module")
def texto():
    with open(RUTA, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def wf(texto):
    return yaml.safe_load(texto)


def pasos(wf):
    for nombre, job in wf["jobs"].items():
        for paso in job.get("steps", []) or []:
            yield nombre, paso


def usos(wf):
    """Todas las referencias `uses:` (de pasos y de jobs reutilizables)."""
    res = [p["uses"] for _, p in pasos(wf) if "uses" in p]
    res += [j["uses"] for j in wf["jobs"].values() if "uses" in j]
    return res


def test_permisos_del_workflow_vacios(wf):
    assert wf.get("permissions") == {}


def test_cada_job_declara_sus_permisos(wf):
    for nombre, job in wf["jobs"].items():
        assert "permissions" in job, f"el job {nombre} no declara permissions"
        assert set(job["permissions"]) <= {"contents"}
        assert job["permissions"].get("contents", "read") in ("read", "write")


def test_uses_externos_fijados_por_sha(wf):
    externos = [u for u in usos(wf) if not u.startswith("./")]
    assert externos, "se esperaban actions externas"
    for u in externos:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u), f"no fijada por SHA: {u}"


def test_uses_con_los_sha_y_tags_acordados(texto):
    esperados = {
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262": "v4.4.0",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065": "v5.6.0",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02": "v4.6.2",
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093": "v4.3.0",
    }
    for ref, tag in esperados.items():
        assert re.search(re.escape(ref) + r"\s+#\s*" + re.escape(tag), texto), ref


def test_comentario_con_tag_en_cada_uses_externo(texto):
    for linea in texto.splitlines():
        m = re.match(r"\s*-?\s*uses:\s*(\S+)(.*)", linea)
        if m and not m.group(1).startswith("./"):
            assert re.search(r"#\s*v\d", m.group(2)), f"falta comentario del tag: {linea}"


def test_sin_softprops(texto):
    assert "softprops" not in texto


def test_ningun_run_interpola_entradas_no_confiables(wf):
    for nombre, paso in pasos(wf):
        run = paso.get("run", "")
        assert "inputs." not in run, f"{nombre}: run con inputs."
        assert "github.ref_name" not in run, f"{nombre}: run con github.ref_name"


def test_sin_interpolacion_peligrosa_en_ningun_run(wf):
    for nombre, paso in pasos(wf):
        run = paso.get("run", "")
        for peligro in ("github.head_ref", "github.event.", "github.ref }}"):
            assert peligro not in run, f"{nombre}: {peligro}"


def test_job_version_primero_y_valida_con_regex(wf, texto):
    assert "version" in wf["jobs"]
    assert next(iter(wf["jobs"])) == "version"
    assert "outputs" in wf["jobs"]["version"]
    assert {"version", "publicar"} <= set(wf["jobs"]["version"]["outputs"])
    assert r"^v?[0-9]+\.[0-9]+\.[0-9]+$" in texto


def test_version_py_se_genera_con_python(texto):
    assert "json.dumps(version)" in texto.replace(" ", "") or "json.dumps(" in texto
    assert not re.search(r"echo\s+.*version\.py", texto)


def test_pruebas_reutiliza_tests_yml_y_compilar_depende(wf):
    assert wf["jobs"]["pruebas"]["uses"] == "./.github/workflows/tests.yml"
    needs = wf["jobs"]["compilar"]["needs"]
    assert {"version", "pruebas"} <= set(needs)


def test_tests_yml_es_reutilizable():
    with open(os.path.join(RAIZ, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        t = yaml.safe_load(f)
    disparadores = t.get(True, t.get("on"))  # PyYAML lee `on:` como True
    assert "workflow_call" in disparadores


def test_solo_el_job_borrador_tiene_contents_write(wf):
    con_escritura = [n for n, j in wf["jobs"].items()
                     if (j.get("permissions") or {}).get("contents") == "write"]
    assert con_escritura == ["borrador"]


def test_borrador_solo_si_publicar_y_necesita_compilar(wf):
    job = wf["jobs"]["borrador"]
    needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
    assert "compilar" in needs
    assert "publicar" in str(job.get("if", ""))


def test_borrador_crea_release_en_borrador_y_nunca_publica(wf):
    run = "\n".join(p.get("run", "") for p in wf["jobs"]["borrador"]["steps"])
    assert "gh release create" in run
    assert "--draft" in run
    assert "--draft=false" not in run
    assert "gh release edit" not in run
    assert "--target" in run


def test_nombres_heredados_no_aparecen_en_el_workflow(texto):
    for nombre in HEREDADOS:
        assert nombre not in texto


def test_nombres_heredados_no_aparecen_en_workflows_ni_en_py_de_la_app():
    rutas = glob.glob(os.path.join(RAIZ, "*.py"))
    rutas += glob.glob(os.path.join(RAIZ, ".github", "workflows", "*.yml"))
    assert rutas
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        for nombre in HEREDADOS:
            assert nombre not in contenido, f"{nombre} en {os.path.relpath(ruta, RAIZ)}"
