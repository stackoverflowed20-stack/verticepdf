"""Tema escuro, ícones e widgets reutilizáveis do Vértice PDF."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

ACCENT = "#1f4fe0"


def last_dir() -> str:
    d = QSettings("VerticePDF", "VerticePDF").value("last_dir", "")
    return d if d and Path(d).is_dir() else str(Path.home())


def remember_dir(path: str | None) -> None:
    if path:
        p = Path(path)
        QSettings("VerticePDF", "VerticePDF").setValue("last_dir", str(p if p.is_dir() else p.parent))


# ---- tokens de design (claro e escuro) ------------------------------------------
LIGHT = dict(NAVY="#0f2340", BG0="#ffffff", BG1="#f5f6f8", BG2="#ffffff", BG3="#e8ecf2", BORDER="#e4e7ec",
             TEXT="#0e1a2b", DIM="#475467", FAINT="#98a2b3", ACCENT_HI="#183fb8", ACCENT_LO="#112f8f",
             CANVAS="#dde3ec", TABBAR="#e9ecf1", SOFT="#f8faff", HOVER2="#eef1f6", PROPBAR="#f7f9fc",
             SIDEPANE="#eef1f6", SCROLL="#c3ccd9", SCROLL_HI="#9aa5b5", PRIMARY_DIS="#a9bbf0",
             TAB_HOVER="#f0f2f6", DROP="rgba(245,246,248,0.95)", ICON="#3d4b5e", ICON_DIS="#b4bdca", INDICATOR="#9aa5b5",
             TINT="#eaf0ff", DASH="#b9c6e4", FIELD="#d0d5dd", THUMB="#eef1f5", CHIP_ON="#0f2340", CHIP_TX="#ffffff",
             TABLINE="#dce0e7", ACCENT_TX="#1f4fe0")
DARK = dict(NAVY="#0a1424", BG0="#1b222d", BG1="#141a23", BG2="#222b38", BG3="#2c3748", BORDER="#2f3a4b",
            TEXT="#e6ebf2", DIM="#9aa8bc", FAINT="#66748a", ACCENT_HI="#4c86ee", ACCENT_LO="#1a4fb3",
            CANVAS="#0e1319", TABBAR="#10161e", SOFT="#27344a", HOVER2="#27344a", PROPBAR="#18202b",
            SIDEPANE="#181f29", SCROLL="#3a4659", SCROLL_HI="#546178", PRIMARY_DIS="#2c4a80",
            TAB_HOVER="#1f2835", DROP="rgba(20,26,35,0.95)", ICON="#c4cedd", ICON_DIS="#4a566a", INDICATOR="#66748a",
            TINT="#22304d", DASH="#3b4a66", FIELD="#3a4659", THUMB="#10161e", CHIP_ON="#e6ebf2", CHIP_TX="#0e1a2b",
            TABLINE="#222b38", ACCENT_TX="#7fa4ff")
MODE = "light"
NAVY = BG0 = BG1 = BG2 = BG3 = BORDER = TEXT = DIM = FAINT = ACCENT_HI = ACCENT_LO = CANVAS = TABBAR = ""
SOFT = HOVER2 = PROPBAR = SIDEPANE = SCROLL = SCROLL_HI = PRIMARY_DIS = TAB_HOVER = DROP = INDICATOR = ""
TINT = DASH = FIELD = THUMB = CHIP_ON = CHIP_TX = TABLINE = ACCENT_TX = ""


def set_theme(mode: str) -> None:
    """Troca os tokens globais ("light" ou "dark"). build_qss() lê estes valores a cada chamada."""
    global MODE
    MODE = "dark" if mode == "dark" else "light"
    t = DARK if MODE == "dark" else LIGHT
    g = globals()
    for k, v in t.items():
        if k in ("ICON", "ICON_DIS"):
            continue
        g[k] = v
    from icons import set_icon_theme
    set_icon_theme(t["ICON"], t["ICON_DIS"])


def system_mode() -> str:
    try:
        from PySide6.QtGui import QGuiApplication
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:  # noqa: BLE001
        return "light"


def appearance_pref() -> str:
    v = QSettings("VerticePDF", "VerticePDF").value("appearance", "system")
    return v if v in ("system", "light", "dark") else "system"


def effective_mode(pref: str | None = None) -> str:
    pref = pref or appearance_pref()
    return system_mode() if pref == "system" else pref


set_theme("light")


def _make_assets() -> str:
    """Gera os PNGs usados pelo QSS (setas, check, fechar) e devolve a pasta."""
    import tempfile
    folder = Path(tempfile.gettempdir()) / f"verticepdf_ui_{MODE}"
    folder.mkdir(exist_ok=True)

    def draw(name: str, painter_fn, size: int = 24, color: str | None = None) -> None:
        color = color or DIM
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), size / 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter_fn(p, size)
        p.end()
        pm.save(str(folder / name), "PNG")

    draw("chev_down.png", lambda p, s: (p.drawLine(int(s * .28), int(s * .4), s // 2, int(s * .62)),
                                        p.drawLine(s // 2, int(s * .62), int(s * .72), int(s * .4))))
    draw("chev_up.png", lambda p, s: (p.drawLine(int(s * .28), int(s * .6), s // 2, int(s * .38)),
                                      p.drawLine(s // 2, int(s * .38), int(s * .72), int(s * .6))))
    draw("check.png", lambda p, s: (p.drawLine(int(s * .26), int(s * .52), int(s * .43), int(s * .68)),
                                    p.drawLine(int(s * .43), int(s * .68), int(s * .76), int(s * .32))),
         color="#ffffff")
    draw("close.png", lambda p, s: (p.drawLine(int(s * .32), int(s * .32), int(s * .68), int(s * .68)),
                                    p.drawLine(int(s * .68), int(s * .32), int(s * .32), int(s * .68))))
    return folder.as_posix()


def build_qss() -> str:
    a = _make_assets()
    return f"""
QWidget {{ font-family: "Geist", "Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG1}; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 28px; font-weight: 650; color: {TEXT}; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#tooltitle {{ font-weight: 600; color: {TEXT}; }}
QToolTip {{ background: {NAVY}; color: #ffffff; border: 0; padding: 5px 9px; }}

/* abas de documentos */
QTabWidget::pane {{ border: 0; }}
QTabBar {{ background: {TABBAR}; }}
QTabBar::tab {{ background: transparent; color: {DIM}; padding: 0 12px 0 12px; margin: 8px 2px 0 2px; height: 32px;
                border-top-left-radius: 8px; border-top-right-radius: 8px; min-width: 84px; font-weight: 500; }}
QTabBar::tab:selected {{ background: {BG0}; color: {TEXT}; }}
QTabBar::tab:hover:!selected {{ background: {TAB_HOVER}; color: {TEXT}; }}
/* abas do painel lateral */
QTabWidget#sidetabs::pane {{ border: 0; background: {SIDEPANE}; }}
QTabWidget#sidetabs QTabBar {{ background: {SIDEPANE}; }}
QTabWidget#sidetabs QTabBar::tab {{ margin: 8px 2px 6px 2px; padding: 6px 12px; min-width: 0;
                border-radius: 8px; }}
QTabWidget#sidetabs QTabBar::tab:selected {{ background: rgba(31,79,224,0.12); color: {ACCENT}; border-bottom: 0; }}

/* botões */
QPushButton {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px;
               padding: 7px 16px; color: {TEXT}; }}
QPushButton:hover {{ background: {BG3}; }}
QPushButton:pressed {{ background: {BG3}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {FAINT}; background: {BG1}; border-color: {BORDER}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton#primary:pressed {{ background: {ACCENT_LO}; }}
QPushButton#primary:disabled {{ background: {PRIMARY_DIS}; border-color: {PRIMARY_DIS}; color: #ffffff; }}
QPushButton#ghost {{ background: transparent; border: 0; color: {DIM}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ background: {BG2}; color: {TEXT}; }}

QToolButton {{ background: transparent; border: 0; border-radius: 8px; padding: 6px 9px; color: {TEXT}; }}
QToolButton:hover {{ background: {BG3}; }}
QToolButton:pressed {{ background: {BG3}; }}
QToolButton:checked {{ background: {ACCENT}; color: white; }}
QToolButton:disabled {{ color: {FAINT}; }}
QToolButton::menu-indicator {{ image: url({a}/chev_down.png); width: 10px; height: 10px;
                               subcontrol-origin: padding; subcontrol-position: right center; right: 2px; }}
QToolButton::menu-button {{ border: 0; width: 16px; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QToolButton::menu-arrow {{ image: url({a}/chev_down.png); width: 10px; height: 10px; }}

/* campos */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG0}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 10px;
    color: {TEXT}; selection-background-color: {ACCENT}; selection-color: white; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; background: {BG1}; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
        width: 20px; border: 0; background: transparent; margin-top: 2px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
        width: 20px; border: 0; background: transparent; margin-bottom: 2px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({a}/chev_up.png); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({a}/chev_down.png); width: 10px; height: 10px; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ border: 0; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({a}/chev_down.png); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
        outline: 0; selection-background-color: {ACCENT}; selection-color: white; }}

QCheckBox, QRadioButton {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {INDICATOR};
        background: {BG0}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {DIM}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({a}/check.png); }}
QRadioButton::indicator:checked {{ border-color: {ACCENT};
        background: qradialgradient(cx:.5, cy:.5, radius:.5, fx:.5, fy:.5,
                    stop:0 {ACCENT}, stop:0.5 {ACCENT}, stop:0.56 {BG0}, stop:1 {BG0}); }}

/* listas e árvores */
QListWidget, QTreeWidget {{ background: {BG0}; border: 1px solid {BORDER}; border-radius: 10px; outline: 0; padding: 4px; }}
QListWidget::item, QTreeWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {BG2}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: rgba(31,79,224,0.13); color: {TEXT}; }}
QHeaderView::section {{ background: transparent; color: {DIM}; border: 0; padding: 6px; }}
QListWidget#thumbs {{ background: transparent; border: 0; padding: 4px 8px; }}
QListWidget#thumbs::item {{ color: {DIM}; border: 1px solid transparent; border-radius: 10px; padding: 8px; }}
QListWidget#thumbs::item:selected {{ background: rgba(31,79,224,0.10); border: 1px solid {ACCENT}; color: {ACCENT}; }}
QTreeWidget#toc {{ background: transparent; border: 0; }}
QListWidget#thumbs::item {{ background: transparent; }}

/* barras do visualizador */
QToolBar {{ background: transparent; border: 0; spacing: 2px; padding: 0; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; height: 1px; margin: 6px 7px; }}
QWidget#topbar {{ background: {BG0}; border-bottom: 1px solid {BORDER}; }}
QWidget#topbar QToolButton {{ padding: 4px 8px; }}
QWidget#titlecorner {{ background: {TABBAR}; }}
QToolButton#filebtn {{ padding: 4px 8px 4px 10px; font-weight: 500; color: {TEXT}; }}
QToolButton#winbtn {{ background: transparent; border: 0; border-radius: 0; padding: 0; min-width: 46px; max-width: 46px; }}
QToolButton#winbtn:hover {{ background: {HOVER2}; }}
QToolButton#winclose {{ background: transparent; border: 0; border-radius: 0; padding: 0; min-width: 46px; max-width: 46px; }}
QToolButton#winclose:hover {{ background: #e81123; }}
QWidget#propbar {{ background: {PROPBAR}; border-bottom: 1px solid {BORDER}; }}
QWidget#ribbon {{ background: {BG0}; border-bottom: 1px solid {BORDER}; }}
QFrame#ribsep {{ background: {BORDER}; border: 0; }}
QTabBar#ribbontabs {{ background: transparent; }}
QTabBar#ribbontabs::tab {{ background: transparent; color: {DIM}; padding: 7px 9px 6px 9px; margin: 0 1px;
    border: 0; border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar#ribbontabs::tab:hover {{ color: {TEXT}; }}
QTabBar#ribbontabs::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QToolButton#rb {{ padding: 4px 10px; border-radius: 8px; color: {TEXT}; }}
QToolButton#rb:hover {{ background: {HOVER2}; }}
QToolButton#rb:checked {{ background: {ACCENT}; color: #ffffff; }}
QToolButton#rb:disabled {{ color: {FAINT}; }}
QToolButton#rb::menu-indicator {{ image: none; width: 0; }}
QWidget#statusbar {{ background: {BG0}; border-top: 1px solid {BORDER}; }}
QWidget#sidepanel {{ background: {BG0}; }}
QWidget#pages {{ background: {CANVAS}; }}
QScrollArea {{ border: 0; background: {CANVAS}; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QLabel#toast {{ background: {NAVY}; border: 0; border-radius: 10px; padding: 10px 18px; color: #ffffff; }}
QLabel#dropzone {{ background: {DROP}; border: 2px dashed {ACCENT}; border-radius: 20px;
                  font-size: 22px; font-weight: 600; color: {TEXT}; }}

/* cards da tela inicial */
QFrame#wordbar {{ background: {NAVY}; border-radius: 8px; border: 1px solid #1d3b61; }}
QFrame#wordbar QLineEdit {{ background: #ffffff; color: #1c2735; border: 1px solid #3a78e6; border-radius: 4px; padding: 3px 6px; }}
QFrame#wordbar QComboBox {{ background: #16365c; color: white; border: 1px solid #2b4a74; border-radius: 4px; padding: 2px 6px; min-width: 70px; }}
QFrame#wordbar QComboBox QAbstractItemView {{ background: white; color: #1c2735; selection-background-color: {ACCENT}; }}
QFrame#wordbar QDoubleSpinBox {{ background: #16365c; color: white; border: 1px solid #2b4a74; border-radius: 4px; padding: 2px 2px; min-width: 46px; max-width: 58px; }}
QFrame#wordbar QToolButton {{ background: transparent; color: white; border: 1px solid transparent; border-radius: 4px; min-width: 24px; min-height: 24px; font-weight: 600; }}
QFrame#wordbar QToolButton:hover {{ background: #22446f; }}
QFrame#wordbar QToolButton:checked {{ background: {ACCENT}; }}
QFrame#wordbar QPushButton {{ background: #16365c; color: white; border: 1px solid #2b4a74; border-radius: 4px; padding: 4px 8px; }}
QFrame#wordbar QPushButton:hover {{ background: #22446f; }}
QFrame#wordbar QPushButton#wb_ok {{ background: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
QFrame#wordbar QPushButton#wb_ok:hover {{ background: {ACCENT_HI}; }}
QFrame#card, QFrame#recent {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#card:hover, QFrame#recent:hover {{ background: {BG2}; border-color: {ACCENT}; }}
QFrame#card QLabel, QFrame#recent QLabel {{ background: transparent; border: 0; }}
QFrame#recent QLabel#thumb {{ background: {THUMB}; border-radius: 8px; }}
QFrame#recent QLabel#stamp {{ background: {BG0}; color: {DIM}; border: 1px solid {BORDER}; border-radius: 9px;
                padding: 1px 8px; font-size: 11px; font-weight: 500; }}
QFrame#card QLabel#badge, QLabel#badge {{ background: {TINT}; color: {ACCENT_TX}; border-radius: 9px;
                padding: 1px 8px; font-size: 11px; font-weight: 700; }}
QToolButton#more {{ background: transparent; border: 0; border-radius: 6px; color: {DIM}; font-size: 16px; font-weight: 700; padding: 0 4px; }}
QToolButton#more:hover {{ background: {BG1}; color: {TEXT}; }}
QToolButton#more::menu-indicator {{ image: none; width: 0; }}
QWidget#sidebar {{ background: {BG0}; border-right: 1px solid {BORDER}; }}
QWidget#sidebar QLabel {{ color: {TEXT}; background: transparent; }}
QWidget#sidebar QLabel#dim {{ color: {DIM}; }}
QLabel#brandname {{ font-size: 16px; font-weight: 650; color: {TEXT}; }}
QLabel#mono {{ font-family: "Geist Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; color: {FAINT}; }}
QPushButton#nav {{ background: transparent; border: 0; border-radius: 8px; color: {DIM}; font-weight: 500;
                   text-align: left; padding: 9px 12px; }}
QPushButton#nav:hover {{ background: {BG1}; color: {TEXT}; }}
QPushButton#nav[active="true"] {{ background: {TINT}; color: {ACCENT_TX}; font-weight: 600; }}
QWidget#home {{ background: {BG1}; }}
QScrollArea#homescroll {{ background: {BG1}; }}
QLineEdit#search {{ background: {BG0}; border: 1px solid {FIELD}; border-radius: 10px; padding: 0 12px 0 4px; min-height: 42px; color: {TEXT}; }}
QLineEdit#search:focus {{ border: 1px solid {ACCENT}; }}
QLabel#kbd {{ background: {BG1}; color: {DIM}; border: 1px solid {BORDER}; border-radius: 5px; padding: 1px 6px;
              font-family: "Geist Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 11px; }}
QFrame#dz {{ background: {BG0}; border: 1px dashed {DASH}; border-radius: 14px; }}
QFrame#dz QLabel {{ background: transparent; border: 0; }}
QLabel#group {{ color: {DIM}; font-size: 12px; font-weight: 600; }}
QPushButton#chip {{ background: {BG0}; border: 1px solid {FIELD}; border-radius: 15px; color: {DIM}; padding: 0 14px; min-height: 30px; max-height: 30px; font-weight: 500; }}
QPushButton#chip:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#chip:checked {{ background: {CHIP_ON}; border-color: {CHIP_ON}; color: {CHIP_TX}; }}
QPushButton#outline {{ background: {BG0}; border: 1px solid {FIELD}; color: {TEXT}; font-weight: 600; }}
QPushButton#outline:hover {{ background: {BG1}; }}

QProgressBar {{ border: 0; border-radius: 4px; background: {BG3}; min-height: 8px; max-height: 8px; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QMenu {{ background: {BG2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 6px; color: {TEXT}; }}
QMenu::item:selected {{ background: {BG3}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SCROLL}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {SCROLL_HI}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SCROLL}; border-radius: 4px; min-width: 36px; }}
QScrollBar::handle:horizontal:hover {{ background: {SCROLL_HI}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


class PolishedDialog(QDialog):
    """Base dos diálogos do app: margens e espaçamento consistentes."""

    def showEvent(self, e):  # noqa: N802
        if not self.property("_polished"):
            self.setProperty("_polished", True)
            lay = self.layout()
            if lay is not None:
                lay.setContentsMargins(24, 22, 24, 20)
                lay.setSpacing(12)
        super().showEvent(e)


class Toast(QLabel):
    """Aviso rápido e não bloqueante (some sozinho)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = 2400) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(ms)

    def reposition(self) -> None:
        p = self.parentWidget()
        if p is not None:
            self.move((p.width() - self.width()) // 2, p.height() - self.height() - 56)


class ResponsiveGrid(QWidget):
    """Grade que ajusta o número de colunas à largura disponível."""

    def __init__(self, min_w: int = 240, spacing: int = 12, parent=None):
        super().__init__(parent)
        self.min_w, self.spacing = min_w, spacing
        self.items: list[QWidget] = []
        self._cols = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)

    def set_items(self, widgets: list[QWidget]) -> None:
        for w in self.items:
            self.grid.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self.items = list(widgets)
        self._cols = 0
        self._relayout()

    def _relayout(self) -> None:
        cols = max(1, (self.width() + self.spacing) // (self.min_w + self.spacing))
        if cols == self._cols and self.grid.count() == len(self.items):
            return
        for w in self.items:
            self.grid.removeWidget(w)
        for c in range(max(cols, self._cols) + 1):
            self.grid.setColumnStretch(c, 0)
        for i, w in enumerate(self.items):
            self.grid.addWidget(w, i // cols, i % cols)
            w.show()
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self._cols = cols

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._relayout()


def apply_theme(app: QApplication, pref: str | None = None) -> None:
    set_theme(effective_mode(pref))
    app.setStyle("Fusion")
    pal = QPalette()
    c = QColor
    pal.setColor(QPalette.Window, c(BG1))
    pal.setColor(QPalette.WindowText, c(TEXT))
    pal.setColor(QPalette.Base, c(BG0))
    pal.setColor(QPalette.AlternateBase, c(BG1))
    pal.setColor(QPalette.Text, c(TEXT))
    pal.setColor(QPalette.Button, c(BG2))
    pal.setColor(QPalette.ButtonText, c(TEXT))
    pal.setColor(QPalette.Highlight, c(ACCENT))
    pal.setColor(QPalette.HighlightedText, c("#ffffff"))
    pal.setColor(QPalette.Disabled, QPalette.Text, c(FAINT))
    pal.setColor(QPalette.ToolTipBase, c(NAVY))
    pal.setColor(QPalette.ToolTipText, c("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, c(FAINT))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c(FAINT))
    app.setPalette(pal)
    app.setStyleSheet(build_qss())
    from icons import refresh_icons
    refresh_icons(app)


def glyph_icon(text: str, color: str, size: int = 36) -> QIcon:
    """Ícone simples: quadrado arredondado colorido com um símbolo."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(0, 0, size, size, size * 0.24, size * 0.24)
    font = QFont("Segoe UI Symbol")
    font.setBold(True)
    font.setPixelSize(int(size * (0.34 if len(text) > 2 else 0.54)))
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------
# Execução em segundo plano
# --------------------------------------------------------------------------
class Worker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            result = self.fn(lambda cur, total: self.progress.emit(cur, total))
        except Exception as exc:  # noqa: BLE001 - mostramos qualquer erro ao usuário
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


class TaskDialog(PolishedDialog):
    """Diálogo com área de conteúdo (self.body) + barra de progresso."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(580)
        root = QVBoxLayout(self)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.content)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._worker: Worker | None = None
        self.result_path: str | None = None

    def start(self, fn: Callable, on_done: Callable[[object], None]) -> None:
        self.content.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText("Processando…")
        w = Worker(fn, self)
        w.progress.connect(self._on_progress)
        w.done.connect(lambda res: self._finish(on_done, res))
        w.failed.connect(self._fail)
        self._worker = w
        w.start()

    def done(self, result: int) -> None:
        w = self._worker
        if w is not None and w.isRunning():     # nunca destrói o diálogo com a thread ainda terminando
            w.wait(3000)
        super().done(result)

    def _on_progress(self, cur: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(cur)

    def _reset(self) -> None:
        self.content.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText("")

    def _finish(self, on_done: Callable, res: object) -> None:
        self._reset()
        on_done(res)

    def _fail(self, msg: str) -> None:
        self._reset()
        QMessageBox.critical(self, "Erro", msg)


# --------------------------------------------------------------------------
# Seletores
# --------------------------------------------------------------------------
class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, mode: str, title: str, filt: str = "PDF (*.pdf)",
                 placeholder: str = "", parent=None):
        super().__init__(parent)
        self.mode, self.title, self.filt = mode, title, filt
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("Procurar…")
        btn.clicked.connect(self.browse)
        h.addWidget(self.edit, 1)
        h.addWidget(btn)

    def browse(self) -> None:
        start = self.edit.text().strip() or last_dir()
        if self.mode == "open":
            path, _ = QFileDialog.getOpenFileName(self, self.title, start, self.filt)
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, self.title, start, self.filt)
        else:
            path = QFileDialog.getExistingDirectory(self, self.title, start)
        if path:
            remember_dir(path)
            self.edit.setText(path)
            self.changed.emit(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


class FileList(QWidget):
    """Lista de arquivos com adicionar/remover/reordenar e arrastar-e-soltar."""

    def __init__(self, single: bool = False, exts: tuple[str, ...] = (".pdf",),
                 filt: str = "PDF (*.pdf)", parent=None):
        super().__init__(parent)
        self.single, self.exts, self.filt = single, exts, filt
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setMinimumHeight(130)
        v.addWidget(self.list)
        h = QHBoxLayout()
        v.addLayout(h)
        for text, slot in (("Adicionar…", self._browse), ("Remover", self._remove),
                           ("Limpar", self.list.clear)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            h.addWidget(b)
        if not single:
            for text, delta in (("▲", -1), ("▼", 1)):
                b = QPushButton(text)
                b.setFixedWidth(40)
                b.setStyleSheet("padding: 7px 0;")
                b.setToolTip("Mover para cima" if delta < 0 else "Mover para baixo")
                b.clicked.connect(lambda _=False, d=delta: self._move(d))
                h.addWidget(b)
        h.addStretch(1)

    def files(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def add_files(self, paths: list[str]) -> None:
        for p in paths:
            if not p.lower().endswith(self.exts):
                continue
            if self.single:
                self.list.clear()
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.list.addItem(item)
            if self.single:
                break

    def _browse(self) -> None:
        if self.single:
            p, _ = QFileDialog.getOpenFileName(self, "Escolher arquivo", last_dir(), self.filt)
            paths = [p] if p else []
        else:
            paths, _ = QFileDialog.getOpenFileNames(self, "Escolher arquivos", last_dir(), self.filt)
        if paths:
            remember_dir(paths[0])
        self.add_files(paths)

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _move(self, delta: int) -> None:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if delta > 0:
            rows.reverse()
        for r in rows:
            new = r + delta
            if 0 <= new < self.list.count():
                self.list.insertItem(new, self.list.takeItem(r))
                self.list.item(new).setSelected(True)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        self.add_files([u.toLocalFile() for u in e.mimeData().urls()])
