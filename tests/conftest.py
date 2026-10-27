import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _qt_cleanup():
    """Depois de cada teste: fecha janelas, executa exclusões pendentes e esvazia a fila de eventos,
    para que timers/eventos de um teste nunca disparem dentro do seguinte."""
    yield
    try:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    for _ in range(3):
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    gc.collect()
