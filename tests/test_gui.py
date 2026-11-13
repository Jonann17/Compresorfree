"""GUI: cerrar la ventana en plena compresion (garantia 5). Necesita display y FFmpeg."""
import faulthandler
import glob
import time

import pytest

from conftest import FFMPEG, generar_video, temporales

TOPE = 120  # s: si algo se cuelga, el proceso de pruebas aborta en vez de bloquear el CI


def _hay_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:  # sin tkinter o TclError "no display"
        return False


pytestmark = [
    pytest.mark.skipif(FFMPEG is None, reason="FFmpeg no disponible"),
    pytest.mark.skipif(not _hay_display(), reason="sin tkinter o sin display (usa xvfb-run)"),
]


def _widgets(widget):
    for w in widget.winfo_children():
        yield w
        yield from _widgets(w)


@pytest.mark.parametrize("con_actualizacion", [False, True],
                         ids=["cierre", "actualizacion_durante_la_compresion"])
def test_cerrar_con_si_durante_la_compresion_no_deja_nada(tmp_path, monkeypatch,
                                                         con_actualizacion):
    """Con con_actualizacion, la busqueda automatica encuentra una version nueva en
    plena compresion: no debe ofrecerse ni instalarse (cerraria la app a medias)."""
    import tkinter
    from tkinter import filedialog, messagebox

    import actualizador
    import app
    import procesos

    video = generar_video(str(tmp_path / "largo.avi"), 30, "960x540")
    monkeypatch.setattr(filedialog, "askopenfilenames", lambda *a, **k: (video,))
    preguntas, descargas = [], []
    monkeypatch.setattr(messagebox, "askyesno", lambda titulo, *a, **k: preguntas.append(titulo) or True)
    if con_actualizacion:
        monkeypatch.setattr(actualizador, "buscar_actualizacion",
                            lambda: {"version": "9.9.9", "url": "http://x/a.zip", "notas": ""})
        monkeypatch.setattr(actualizador, "es_app_compilada", lambda: True)
        monkeypatch.setattr(actualizador, "descargar", lambda *a, **k: descargas.append(a))
        monkeypatch.setattr(actualizador, "instalar", lambda *a, **k: descargas.append(a))
    else:
        monkeypatch.setattr(actualizador, "buscar_actualizacion", lambda: None)
    cierre = []

    guardados, errores = [], []
    original = tkinter.Tk.mainloop

    def mainloop_guion(ventana, n=0):
        def falla(e):
            errores.append(repr(e))
            ventana.destroy()

        def boton(texto):
            for w in _widgets(ventana):
                try:
                    if w.cget("text") == texto:
                        return w
                except tkinter.TclError:
                    pass
            raise AssertionError(f"no hay boton {texto!r}")

        def pulsar():
            try:
                boton("Agregar...").invoke()
                boton("Comprimir").invoke()
                sondear(time.monotonic() + 30)
            except Exception as e:  # noqa: BLE001
                falla(e)

        def sondear(limite):
            try:
                for p in procesos.procesos_vivos():
                    if p not in guardados:
                        guardados.append(p)
                codificando = any("-progress" in map(str, p.args) for p in guardados)
                # Con actualizacion se espera a que la busqueda automatica (1,5 s) responda.
                if codificando and (not con_actualizacion or time.monotonic() > inicio + 3):
                    cierre.append(time.monotonic())
                    manejador = ventana.protocol("WM_DELETE_WINDOW")
                    ventana.tk.call(manejador)
                elif time.monotonic() > limite:
                    raise AssertionError("la codificacion nunca arranco")
                else:
                    ventana.after(50, lambda: sondear(limite))
            except Exception as e:  # noqa: BLE001
                falla(e)

        inicio = time.monotonic()
        ventana.after(500, pulsar)
        original(ventana, n)

    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop_guion)

    faulthandler.dump_traceback_later(TOPE, exit=True)
    try:
        app.iniciar_gui()
    finally:
        faulthandler.cancel_dump_traceback_later()

    assert errores == []
    assert guardados, "no se vio ningun proceso hijo"
    assert cierre and time.monotonic() - cierre[0] < 10, "el cierre no debe llegar al tope de 15 s"
    assert preguntas == ["Tarea en curso"], preguntas
    assert descargas == [], "no debe instalarse una actualizacion en plena compresion"
    limite = time.monotonic() + 5
    while time.monotonic() < limite and any(p.poll() is None for p in guardados):
        time.sleep(0.1)
    for p in guardados:
        assert p.poll() is not None, "quedo un proceso hijo vivo"
    assert glob.glob(str(tmp_path / "*_comprimido_*")) == []
    assert temporales(tmp_path) == []
    assert procesos.procesos_vivos() == []
