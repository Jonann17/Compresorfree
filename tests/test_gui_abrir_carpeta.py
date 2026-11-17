"""GUI: el boton 'Abrir carpeta' llama al abridor con la carpeta del resultado."""
import faulthandler
import os
import time

import pytest

from conftest import FFMPEG, generar_video

pytestmark = [pytest.mark.skipif(FFMPEG is None, reason="FFmpeg no disponible")]


def _hay_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _hay_display(), reason="sin tkinter o sin display (usa xvfb-run)")
def test_boton_abrir_carpeta(tmp_path, monkeypatch):
    import tkinter
    from tkinter import filedialog, messagebox

    import actualizador
    import app
    import preferencias

    monkeypatch.setattr(preferencias, "ruta_config", lambda: str(tmp_path / "cfg" / "p.json"))
    video = generar_video(str(tmp_path / "v.avi"), 1, "160x120")
    salida = tmp_path / "out"
    salida.mkdir()
    monkeypatch.setattr(filedialog, "askopenfilenames", lambda *a, **k: (video,))
    monkeypatch.setattr(filedialog, "askdirectory", lambda *a, **k: str(salida))
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(actualizador, "buscar_actualizacion", lambda: None)
    abiertas, errores, estados = [], [], []
    monkeypatch.setattr(app, "abrir_carpeta", lambda c: abiertas.append(c))
    original = tkinter.Tk.mainloop

    def mainloop_guion(ventana, n=0):
        def boton(texto):
            def rec(w):
                for h in w.winfo_children():
                    yield h
                    yield from rec(h)
            for w in rec(ventana):
                try:
                    if w.cget("text") == texto:
                        return w
                except tkinter.TclError:
                    pass
            raise AssertionError(texto)

        def falla(e):
            errores.append(repr(e))
            ventana.destroy()

        def inicio():
            try:
                abrir = boton("Abrir carpeta")
                estados.append(str(abrir.cget("state")))
                boton("Elegir carpeta...").invoke()
                boton("Agregar...").invoke()
                boton("Comprimir").invoke()
                esperar(time.monotonic() + 60)
            except Exception as e:  # noqa: BLE001
                falla(e)

        def esperar(limite):
            try:
                abrir = boton("Abrir carpeta")
                if str(abrir.cget("state")) == "normal":
                    abrir.invoke()
                    ventana.destroy()
                elif time.monotonic() > limite:
                    raise AssertionError("no termino")
                else:
                    ventana.after(100, lambda: esperar(limite))
            except Exception as e:  # noqa: BLE001
                falla(e)

        ventana.after(300, inicio)
        original(ventana, n)

    monkeypatch.setattr(tkinter.Tk, "mainloop", mainloop_guion)
    faulthandler.dump_traceback_later(120, exit=True)
    try:
        app.iniciar_gui()
    finally:
        faulthandler.cancel_dump_traceback_later()
    assert errores == []
    assert estados == ["disabled"]
    assert [os.path.realpath(c) for c in abiertas] == [os.path.realpath(str(salida))]
    assert preferencias.cargar(str(tmp_path / "cfg" / "p.json"))["carpeta"] == str(salida)
