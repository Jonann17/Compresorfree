"""Los objetos de Tk deben liberarse en el hilo principal (si no, Tcl aborta)."""
import subprocess
import sys

import pytest

from conftest import RAIZ

SCRIPT = r"""
import gc, sys, threading
sys.path.insert(0, sys.argv[1])
import tkinter, app, actualizador
actualizador.buscar_actualizacion = lambda: None
tkinter.Tk.mainloop = lambda self, n=0: (self.update(), self.destroy())
gc.disable()
app.iniciar_gui()
t = threading.Thread(target=gc.collect)  # un hilo de trabajo que recolecta despues
t.start(); t.join()
print("ok")
"""


def _hay_display():
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _hay_display(), reason="sin tkinter o sin display")
def test_cerrar_la_gui_no_deja_basura_de_tk_para_otros_hilos():
    r = subprocess.run([sys.executable, "-c", SCRIPT, RAIZ], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    assert "ok" in r.stdout
