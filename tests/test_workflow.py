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


def test_job_version_primero_y_usa_el_script(wf, texto):
    assert next(iter(wf["jobs"])) == "version"
    job = wf["jobs"]["version"]
    assert {"version", "numerica", "tag", "prerelease", "publicar"} <= set(job["outputs"])
    paso = next(p for p in job["steps"] if p.get("id") == "validar")
    assert "tools/version_release.py" in paso["run"]
    # Las entradas llegan por entorno y la logica esta en un script con pruebas.
    assert {"EVENTO", "NOMBRE_REF", "VERSION_MANUAL", "PRERELEASE_MANUAL"} <= set(paso["env"])
    assert any(p.get("uses", "").startswith("actions/checkout@") for p in job["steps"])


def test_ejecutar_el_paso_validar_como_en_actions(wf):
    """Corre la linea real del paso con las variables de entorno y lee GITHUB_OUTPUT."""
    import shutil
    import subprocess
    import sys
    import tempfile
    paso = next(p for p in wf["jobs"]["version"]["steps"] if p.get("id") == "validar")
    # El paso corre en ubuntu con bash; en Windows se usa el bash de Git.
    comando = paso["run"].replace("python3", '"$PY"', 1)
    git_bash = os.path.join(os.environ.get("ProgramFiles", ""), "Git", "bin", "bash.exe")
    # En Windows, el bash de System32 es WSL: se prefiere el de Git.
    bash = git_bash if os.name == "nt" and os.path.exists(git_bash) else shutil.which("bash")
    assert bash, "hace falta bash para ejecutar el paso como en Actions"

    def correr(evento, ref="", manual="", pre=""):
        with tempfile.TemporaryDirectory() as tmp:
            salida = os.path.join(tmp, "salida")
            open(salida, "w").close()
            env = dict(os.environ, EVENTO=evento, NOMBRE_REF=ref, VERSION_MANUAL=manual,
                       PRERELEASE_MANUAL=pre, GITHUB_OUTPUT=salida, PY=sys.executable)
            r = subprocess.run([bash, "-c", comando], env=env, capture_output=True, cwd=RAIZ)
            if r.returncode != 0:
                return None
            return dict(l.split("=", 1) for l in open(salida).read().splitlines() if "=" in l)

    assert correr("push", ref="v1.2.3")["version"] == "1.2.3"
    assert correr("push", ref="v1.3.0-rc.1")["prerelease"] == "true"
    assert correr("workflow_dispatch", manual="1.2.3", pre="false")["prerelease"] == "false"
    assert correr("push")["publicar"] == "false"
    assert correr("workflow_dispatch", manual="1.2") is None
    assert correr("workflow_dispatch", manual="1.2.3\nx=1") is None


def test_version_py_se_genera_con_python(wf):
    escritores = [(n, p) for n, p in pasos(wf) if "version.py" in p.get("run", "")]
    assert escritores, "ningun paso escribe version.py"
    for nombre, paso in escritores:
        run = paso["run"]
        assert paso.get("shell") == "python", f"{nombre}: version.py debe escribirse con python"
        assert "json.dumps(version)" in run.replace(" ", ""), f"{nombre}: sin json.dumps(version)"
        assert not re.search(r"\becho\b", run), f"{nombre}: usa echo"
        assert 'os.environ["VERSION"]' in run  # la version llega por entorno, no interpolada


def test_pruebas_reutiliza_tests_yml_y_compilar_depende(wf):
    assert wf["jobs"]["pruebas"]["uses"] == "./.github/workflows/tests.yml"
    needs = wf["jobs"]["compilar"]["needs"]
    assert {"version", "pruebas"} <= set(needs)


def test_tests_yml_es_reutilizable():
    with open(os.path.join(RAIZ, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        t = yaml.safe_load(f)
    disparadores = t.get(True, t.get("on"))  # PyYAML lee `on:` como True
    assert "workflow_call" in disparadores


def test_solo_el_job_publicar_tiene_contents_write(wf):
    con_escritura = [n for n, j in wf["jobs"].items()
                     if (j.get("permissions") or {}).get("contents") == "write"]
    assert con_escritura == ["publicar"]
    assert "borrador" not in wf["jobs"]


def test_publicar_solo_si_publicar_y_necesita_compilar(wf):
    job = wf["jobs"]["publicar"]
    needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
    assert "compilar" in needs
    assert "publicar" in str(job.get("if", ""))


def test_publicar_crea_release_sin_draft_y_la_completa_si_existe(wf):
    run = "\n".join(p.get("run", "") for p in wf["jobs"]["publicar"]["steps"])
    assert "gh release create" in run
    assert "--draft" not in run.replace("--draft=false", "")
    assert "gh release edit" in run and "--draft=false" in run
    # Un borrador viejo apuntaria al commit en que se creo: el tag debe ser el de este build.
    assert run.count("--target \"$GITHUB_SHA\"") == 2
    assert "gh release upload" in run and "--clobber" in run
    assert "--target" in run and "--notes-file notas_release.md" in run
    assert '--prerelease="$PRERELEASE"' in run
    assert "--generate-notes" not in run


def test_publicar_hace_checkout_sin_credenciales_y_genera_el_manifiesto(wf):
    pasos_ = wf["jobs"]["publicar"]["steps"]
    checkout = next(p for p in pasos_ if p.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False
    run = "\n".join(p.get("run", "") for p in pasos_)
    assert "tools/generar_manifiesto.py" in run and "$GITHUB_SHA" in run


def test_todos_los_checkout_sin_credenciales(wf):
    checkouts = [p for _, p in pasos(wf) if p.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) >= 3
    for p in checkouts:
        assert p["with"]["persist-credentials"] is False


def test_se_compila_el_instalador_y_se_publican_los_nombres_exactos(wf, texto):
    run = "\n".join(p.get("run", "") for _, p in pasos(wf))
    assert "installer/compresorfree.iss" in run
    assert "choco install innosetup -y" in run
    paso = next(p for p in wf["jobs"]["publicar"]["steps"] if p.get("name", "").startswith("Comprobar"))
    for nombre in ("Compresorfree-Setup-{v}.exe", "Compresorfree-{v}-windows-x64.zip",
                   "Compresorfree-{v}-macos-arm64.dmg", "Compresorfree-{v}-macos-x64.dmg",
                   "manifest.json"):
        assert nombre in paso["run"]


def test_nombres_heredados_no_aparecen_en_el_workflow(texto):
    for nombre in HEREDADOS:
        assert nombre not in texto


def test_nombres_heredados_no_aparecen_en_workflows_ni_en_py_de_la_app():
    rutas = glob.glob(os.path.join(RAIZ, "*.py"))
    rutas += glob.glob(os.path.join(RAIZ, "herramientas", "*.py"))
    rutas += glob.glob(os.path.join(RAIZ, ".github", "workflows", "*.yml"))
    assert rutas
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        for nombre in HEREDADOS:
            assert nombre not in contenido, f"{nombre} en {os.path.relpath(ruta, RAIZ)}"


@pytest.fixture(scope="module")
def tests_yml():
    with open(os.path.join(RAIZ, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_tests_yml_permisos_vacios_y_contents_read_por_job(tests_yml):
    assert tests_yml.get("permissions") == {}
    assert tests_yml["jobs"], "tests.yml sin jobs"
    for nombre, job in tests_yml["jobs"].items():
        assert job.get("permissions") == {"contents": "read"}, nombre


def test_tests_yml_checkout_sin_credenciales_y_actions_fijadas(tests_yml):
    for nombre, job in tests_yml["jobs"].items():
        for paso in job["steps"]:
            if "uses" in paso:
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", paso["uses"]), paso["uses"]
            if paso.get("uses", "").startswith("actions/checkout@"):
                assert paso["with"]["persist-credentials"] is False, nombre


def test_herramientas_existen_en_la_busqueda_de_heredados():
    assert glob.glob(os.path.join(RAIZ, "herramientas", "*.py"))


def _validar_version(script, pedida):
    """Ejecuta el script del paso 'validar' como en GitHub Actions; None si falla."""
    import subprocess
    import sys
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        salida = os.path.join(tmp, "salida")
        open(salida, "w").close()
        env = dict(os.environ, ES_TAG="false", NOMBRE_REF="", VERSION_MANUAL=pedida,
                   GITHUB_OUTPUT=salida)
        r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True)
        if r.returncode != 0:
            return None
        valores = dict(l.split("=", 1) for l in open(salida).read().splitlines() if "=" in l)
        return valores.get("version")
