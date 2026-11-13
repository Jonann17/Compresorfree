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


def test_cerrar_con_si_durante_la_compresion_no_deja_nada(tmp_path, monkeypatch):
    import tkinter
    from tkinter import filedialog, messagebox

    import actualizador
    import app
    import procesos

    video = generar_video(str(tmp_path / "largo.avi"), 30, "960x540")
    monkeypatch.setattr(filedialog, "askopenfilenames", lambda *a, **k: (video,))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(actualizador, "buscar_actualizacion", lambda: None)

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
                if any("-progress" in map(str, p.args) for p in guardados):
                    manejador = ventana.protocol("WM_DELETE_WINDOW")
                    ventana.tk.call(manejador)
                elif time.monotonic() > limite:
                    raise AssertionError("la codificacion nunca arranco")
                else:
                    ventana.after(50, lambda: sondear(limite))
            except Exception as e:  # noqa: BLE001
                falla(e)

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
    limite = time.monotonic() + 5
    while time.monotonic() < limite and any(p.poll() is None for p in guardados):
        time.sleep(0.1)
    for p in guardados:
        assert p.poll() is not None, "quedo un proceso hijo vivo"
    assert glob.glob(str(tmp_path / "*_comprimido_*")) == []
    assert temporales(tmp_path) == []
    assert procesos.procesos_vivos() == []
