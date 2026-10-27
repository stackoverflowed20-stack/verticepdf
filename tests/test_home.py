from PySide6.QtWidgets import QApplication

import main


def test_home_search_and_chips():
    QApplication.instance() or QApplication([])
    h = main.HomePage()
    h.show()
    h._on_search("ocr")
    h._on_search("")
    h._set_group(2)
    h._set_group(0)
    h._on_search("zzzz")
    h._on_search("")
    h.deleteLater()
