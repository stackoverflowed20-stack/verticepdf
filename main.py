"""Vértice PDF — editor de PDF desktop (PySide6 + PyMuPDF).

Uso:  python main.py [arquivo.pdf ...]
"""
from __future__ import annotations

import getpass
import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QFont, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QMenu, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTabBar, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

import ops
import recovery
import updater
from dialogs import BatchDialog, CreateDialog, EncryptDialog, OcrDialog, OrganizeDialog, PreferencesDialog, UpdateDialog
import icons
from icons import brand_pixmap, icon, render, soft_tile_pixmap
import ui_common
from ui_common import ResponsiveGrid, Worker, apply_theme, last_dir, remember_dir
from version import APP_NAME, UPDATE_URL, __version__
from viewer import PdfView, pix_to_qpixmap

MAX_RECENT = 20
LOG_PATH = ""

# chave, título, descrição, ícone, cor, selo
TOOLS = {
    "edit": ("Editar PDF", "Altere parágrafos, realce trechos, apague áreas e anote direto na página.", "edit", "#2563eb", ""),
    "form": ("Preencher formulário", "Preencha campos de formulário e assine o documento.", "form", "#4f46e5", ""),
    "ocr": ("OCR PDF", "Reconheça o texto de documentos digitalizados e torne-os pesquisáveis.", "scan", "#0891b2", "Novo"),
    "organize": ("Organizar páginas", "Reordene, gire, duplique, adicione e exclua páginas.", "pages", "#0d9488", ""),
    "batch": ("Processamento em lote", "Combine, divida, comprima e converta vários arquivos de uma vez.", "layers", "#0f4c81", ""),
    "compress": ("Comprimir PDF", "Diminua o tamanho do arquivo mantendo a legibilidade.", "compress", "#6d28d9", ""),
    "create": ("Criar PDF", "Gere uma página em branco ou transforme imagens em PDF.", "plus", "#15803d", ""),
    "share": ("Compartilhar PDF", "Copie o arquivo para colar em e-mail, chat ou pasta compartilhada.", "share", "#0f4c81", ""),
    "print": ("Imprimir PDF", "Envie seu documento para a impressora de forma rápida.", "print", "#475569", ""),
    "encrypt": ("Criptografar PDF", "Proteja o arquivo com senha ou remova a senha existente.", "lock", "#b45309", ""),
}
SECTIONS = [
    ("Editar e anotar", ["edit", "form", "ocr"]),
    ("Organizar e converter", ["organize", "batch", "compress"]),
    ("Criar, compartilhar e proteger", ["create", "share", "print", "encrypt"]),
]


class ToolCard(QFrame):
    triggered = Signal(str)

    def __init__(self, key: str):
        super().__init__()
        title, desc, icon_name, _color, badge = TOOLS[key]
        self.key = key
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(96)
        self.setToolTip(title)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 18, 18, 18)
        row.setSpacing(14)
        tile = QLabel()
        tile.setPixmap(soft_tile_pixmap(icon_name, ui_common.TINT, ui_common.ACCENT_TX, 40))
        tile.setFixedSize(40, 40)
        row.addWidget(tile, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("h2")
        head.addWidget(t)
        if badge:
            b = QLabel(badge)
            b.setObjectName("badge")
            b.setFixedHeight(18)
            head.addWidget(b)
        head.addStretch(1)
        col.addLayout(head)
        d = QLabel(desc)
        d.setObjectName("dim")
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        col.addWidget(d, 1)
        row.addLayout(col, 1)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.triggered.emit(self.key)


class RecentCard(QFrame):
    triggered = Signal(str)
    remove_requested = Signal(str)
    THUMB = QSize(198, 150)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        f = Path(path)
        st = f.stat()
        self.setObjectName("recent")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(path)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedHeight(self.THUMB.height())
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(render("pages", "#b4bdca", 48))
        tl = QVBoxLayout(self.thumb)
        tl.setContentsMargins(8, 8, 8, 8)
        stamp = QLabel(f"{datetime.fromtimestamp(st.st_mtime):%d/%m/%Y}", self.thumb)
        stamp.setObjectName("stamp")
        stamp.setAttribute(Qt.WA_TransparentForMouseEvents)
        tl.addWidget(stamp, 0, Qt.AlignLeft | Qt.AlignBottom)
        v.addWidget(self.thumb)
        row = QHBoxLayout()
        row.setSpacing(4)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel()
        name.setObjectName("h2")
        name.setStyleSheet("font-size: 14px;")
        name.setText(QFontMetrics(name.font()).elidedText(f.name, Qt.ElideMiddle, 160))
        meta = QLabel(ops.fmt_size(st.st_size))
        meta.setObjectName("dim")
        meta.setStyleSheet("font-size: 12.5px;")
        col.addWidget(name)
        col.addWidget(meta)
        row.addLayout(col, 1)
        more = QToolButton()
        more.setObjectName("more")
        more.setText("⋯")
        more.setCursor(Qt.PointingHandCursor)
        more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Abrir", lambda: self.triggered.emit(self.path))
        menu.addAction("Remover da lista", lambda: self.remove_requested.emit(self.path))
        more.setMenu(menu)
        row.addWidget(more, 0, Qt.AlignTop)
        v.addLayout(row)
        for child in (name, meta, stamp):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_thumb(self, pm: QPixmap) -> None:
        self.thumb.setPixmap(pm)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.triggered.emit(self.path)


class HomePage(QWidget):
    open_requested = Signal()
    create_requested = Signal()
    tool_requested = Signal(str)
    recent_requested = Signal(str)
    remove_recent_requested = Signal(str)
    clear_recent_requested = Signal()
    about_requested = Signal()

    def __init__(self):
        super().__init__()
        self._thumb_cache: dict[str, tuple[float, QPixmap]] = {}
        self._recent_paths: list[str] = []
        self._show_all = False
        self._query = ""
        self._group = 0           # 0 = todas
        self._thumb_queue: list[RecentCard] = []
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(15)
        self._thumb_timer.timeout.connect(self._next_thumb)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("home")
        self.scroll.setWidget(page)
        self.scroll.setObjectName("homescroll")
        outer.addWidget(self.scroll, 1)

        v = QVBoxLayout(page)
        v.setContentsMargins(40, 32, 40, 40)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        h1 = QLabel("Central de documentos")
        h1.setObjectName("h1")
        sub = QLabel("Edite, organize, converta e proteja seus PDFs em um só lugar.")
        sub.setObjectName("dim")
        titles.addWidget(h1)
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        head.addWidget(self._build_search(), 0, Qt.AlignTop)
        v.addLayout(head)
        v.addSpacing(8)
        v.addWidget(self._build_dropzone())
        v.addSpacing(10)

        self.recent_box = QWidget()
        rb = QVBoxLayout(self.recent_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(10)
        rh = QHBoxLayout()
        rec = QLabel("Recentes")
        rec.setObjectName("h2")
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("dim")
        rh.addWidget(rec)
        rh.addWidget(self.count_lbl)
        rh.addStretch(1)
        self.more_btn = QPushButton("Ver todos")
        self.more_btn.setObjectName("ghost")
        self.more_btn.clicked.connect(self._toggle_all)
        rh.addWidget(self.more_btn)
        self.clear_btn = QPushButton("Limpar lista")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.clicked.connect(self.clear_recent_requested)
        rh.addWidget(self.clear_btn)
        rb.addLayout(rh)
        self.recent_grid = ResponsiveGrid(min_w=230, spacing=16)
        rb.addWidget(self.recent_grid)
        v.addWidget(self.recent_box)
        v.addSpacing(10)

        self.tools_box = QWidget()
        tb = QVBoxLayout(self.tools_box)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(10)
        th = QHBoxLayout()
        tl = QLabel("Ferramentas")
        tl.setObjectName("h2")
        th.addWidget(tl)
        th.addSpacing(10)
        self._chips: list[QPushButton] = []
        for i, label in enumerate(["Todas"] + [s[0] for s in SECTIONS]):
            c = QPushButton(label)
            c.setObjectName("chip")
            c.setCheckable(True)
            c.setChecked(i == 0)
            c.setCursor(Qt.PointingHandCursor)
            c.clicked.connect(lambda _=False, n=i: self._set_group(n))
            self._chips.append(c)
            th.addWidget(c)
        th.addStretch(1)
        tb.addLayout(th)
        self.tools_host = QVBoxLayout()
        self.tools_host.setSpacing(10)
        tb.addLayout(self.tools_host)
        v.addWidget(self.tools_box)
        v.addStretch(1)
        self._render_tools()

    # ---- partes fixas ----------------------------------------------------------
    def _build_search(self) -> QLineEdit:
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar ferramentas e arquivos")
        self.search.setFixedSize(340, 44)
        self.search.addAction(icon("search", 18), QLineEdit.LeadingPosition)
        self.search.setTextMargins(0, 0, 58, 0)
        lay = QHBoxLayout(self.search)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.addStretch(1)
        kbd = QLabel("Ctrl K")
        kbd.setObjectName("kbd")
        kbd.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(kbd, 0, Qt.AlignVCenter)
        self.search.textChanged.connect(self._on_search)
        self.search.returnPressed.connect(self._search_enter)
        return self.search

    def _build_dropzone(self) -> QFrame:
        dz = QFrame()
        dz.setObjectName("dz")
        row = QHBoxLayout(dz)
        row.setContentsMargins(24, 22, 24, 22)
        row.setSpacing(18)
        tile = QLabel()
        tile.setPixmap(soft_tile_pixmap("download", ui_common.TINT, ui_common.ACCENT_TX, 56, 0.28))
        tile.setFixedSize(56, 56)
        row.addWidget(tile)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Abra ou arraste um PDF para começar")
        t.setObjectName("h2")
        t.setStyleSheet("font-size: 17px;")
        d = QLabel("Solte o arquivo em qualquer parte da janela ou escolha um documento do computador.")
        d.setObjectName("dim")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        row.addLayout(col, 1)
        create_btn = QPushButton("Criar PDF")
        create_btn.setObjectName("outline")
        create_btn.setMinimumHeight(42)
        create_btn.setMinimumWidth(110)
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self.create_requested)
        open_btn = QPushButton("Abrir PDF")
        open_btn.setObjectName("primary")
        open_btn.setMinimumHeight(42)
        open_btn.setMinimumWidth(120)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_requested)
        row.addWidget(create_btn)
        row.addWidget(open_btn)
        return dz

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(232)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 22, 16, 18)
        v.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(brand_pixmap(32))
        logo.setFixedSize(32, 32)
        logo.setScaledContents(True)
        brand.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setObjectName("brandname")
        brand.addWidget(name)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(22)

        self._nav: list[QPushButton] = []
        items = [("Início", "home", self._go_top), ("Recentes", "pages", self._go_recent),
                 ("Ferramentas", "layers", self._go_tools),
                 ("Processamento em lote", "merge", lambda: self.tool_requested.emit("batch"))]
        for i, (label, ic, fn) in enumerate(items):
            b = QPushButton("  " + label)
            b.setObjectName("nav")
            b.setIcon(icon(ic, 18))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("active", i == 0)
            b.clicked.connect(lambda _=False, n=i, f=fn: self._nav_click(n, f))
            self._nav.append(b)
            v.addWidget(b)
        v.addStretch(1)

        about = QPushButton("  Sobre")
        about.setObjectName("nav")
        about.setIcon(icon("info", 18))
        about.setIconSize(QSize(18, 18))
        about.setCursor(Qt.PointingHandCursor)
        about.clicked.connect(self.about_requested)
        v.addWidget(about)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("mono")
        ver.setContentsMargins(12, 4, 0, 0)
        v.addWidget(ver)
        return side

    # ---- navegação e busca -----------------------------------------------------
    def _nav_click(self, n: int, fn) -> None:
        if n < 3:
            for i, b in enumerate(self._nav[:3]):
                b.setProperty("active", i == n)
                b.style().unpolish(b)
                b.style().polish(b)
        fn()

    def _go_top(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)

    def _go_recent(self) -> None:
        self.scroll.verticalScrollBar().setValue(self.recent_box.y() if self.recent_box.isVisible() else 0)

    def _go_tools(self) -> None:
        self.scroll.verticalScrollBar().setValue(self.tools_box.y())

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _on_search(self, text: str) -> None:
        self._query = text.strip().lower()
        self._render_tools()
        self._render_recent()

    def _matches(self, key: str) -> bool:
        if not self._query:
            return True
        title, desc = TOOLS[key][0], TOOLS[key][1]
        return self._query in f"{title} {desc}".lower()

    def _search_enter(self) -> None:
        keys = [k for g, (_t, ks) in enumerate(SECTIONS, 1) if self._group in (0, g) for k in ks if self._matches(k)]
        if len(keys) == 1:
            self.tool_requested.emit(keys[0])

    def _set_group(self, n: int) -> None:
        self._group = n
        for i, c in enumerate(self._chips):
            c.setChecked(i == n)
        self._render_tools()

    def _render_tools(self) -> None:
        while self.tools_host.count():
            it = self.tools_host.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        found = False
        for g, (title, keys) in enumerate(SECTIONS, 1):
            if self._group not in (0, g):
                continue
            keys = [k for k in keys if self._matches(k)]
            if not keys:
                continue
            found = True
            lab = QLabel(title.upper())
            lab.setObjectName("group")
            f = lab.font()
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
            lab.setFont(f)
            self.tools_host.addWidget(lab)
            grid = ResponsiveGrid(min_w=270, spacing=16)
            cards = []
            for k in keys:
                card = ToolCard(k)
                card.triggered.connect(self.tool_requested)
                cards.append(card)
            grid.set_items(cards)
            self.tools_host.addWidget(grid)
            self.tools_host.addSpacing(6)
        if not found:
            none = QLabel("Nenhuma ferramenta encontrada.")
            none.setObjectName("dim")
            self.tools_host.addWidget(none)

    # ---- recentes com miniatura -------------------------------------------
    VISIBLE_RECENT = 8

    def set_recent(self, paths: list[str]) -> None:
        self._recent_paths = [p for p in paths if Path(p).is_file()]
        self._render_recent()

    def _toggle_all(self) -> None:
        self._show_all = not self._show_all
        self._render_recent()

    def _render_recent(self) -> None:
        self._thumb_timer.stop()
        self._thumb_queue = []
        paths = [p for p in self._recent_paths if self._query in Path(p).name.lower()]
        total = len(paths)
        shown = paths if self._show_all else paths[:self.VISIBLE_RECENT]
        cards = []
        for p in shown:
            card = RecentCard(p)
            card.triggered.connect(self.recent_requested)
            card.remove_requested.connect(self.remove_recent_requested)
            cached = self._thumb_cache.get(p)
            if cached and cached[0] == Path(p).stat().st_mtime:
                card.set_thumb(cached[1])
            else:
                self._thumb_queue.append(card)
            cards.append(card)
        self.recent_grid.set_items(cards)
        self.recent_box.setVisible(bool(self._recent_paths) and (bool(cards) or not self._query))
        self.count_lbl.setText(f"{total} arquivo{'s' if total != 1 else ''}" if total else "")
        self.more_btn.setVisible(total > self.VISIBLE_RECENT)
        self.more_btn.setText("Mostrar menos" if self._show_all else f"Ver todos ({total})")
        if self._thumb_queue:
            self._thumb_timer.start()

    def _next_thumb(self) -> None:
        if not self._thumb_queue:
            self._thumb_timer.stop()
            return
        card = self._thumb_queue.pop(0)
        try:
            with fitz.open(card.path) as doc:
                if doc.needs_pass:
                    card.thumb.setPixmap(render("lock", "#8794a7", 48))
                    return
                page = doc[0]
                w, h = card.THUMB.width() - 16, card.THUMB.height() - 16
                s = min(w / page.rect.width, h / page.rect.height) * 2
                pm = pix_to_qpixmap(page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False))
                pm.setDevicePixelRatio(2)
            self._thumb_cache[card.path] = (Path(card.path).stat().st_mtime, pm)
            card.set_thumb(pm)
        except Exception:  # noqa: BLE001 - cartão já pode ter sido removido ou arquivo inválido
            pass


class WinButton(QToolButton):
    """Botão minimizar / maximizar / fechar da barra de título própria."""

    def __init__(self, kind: str, tip: str):
        super().__init__()
        self.kind = kind
        self.setObjectName("winclose" if kind == "win_close" else "winbtn")
        self.setToolTip(tip)
        self.setFixedSize(46, 40)
        self.setFocusPolicy(Qt.NoFocus)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.setIcon(icon("close" if kind == "win_close" else kind, 14))

    def enterEvent(self, e):  # noqa: N802
        if self.kind == "win_close":
            self.setIcon(icon("close", 14, "#ffffff"))
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        if self.kind == "win_close":
            self.setIcon(icon("close", 14))
        super().leaveEvent(e)


class MainWindow(QMainWindow):
    RESIZE_MARGIN = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 780)
        self.setWindowIcon(QIcon(brand_pixmap(64)))
        self.setAcceptDrops(True)
        self.settings = QSettings("VerticePDF", "VerticePDF")
        old = QSettings("MeuPDF", "MeuPDF")  # migra recentes/pasta do nome anterior (uma vez)
        if not self.settings.contains("recent") and old.contains("recent"):
            self.settings.setValue("recent", old.value("recent"))
            if old.contains("last_dir"):
                self.settings.setValue("last_dir", old.value("last_dir"))

        self.setMinimumSize(980, 640)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)  # botões de fechar próprios (ícone vetorial)
        self.tabs.setMovable(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setExpanding(False)
        self.setCentralWidget(self.tabs)

        self.drop = QLabel("Solte o PDF aqui para abrir", self)
        self.drop.setObjectName("dropzone")
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.hide()

        self.home = self._make_home()
        self.tabs.addTab(self.home, QIcon(render("home", icons.ICON_COLOR, 36)), "Início")

        self.setWindowFlag(Qt.FramelessWindowHint, True)   # a barra de título é a própria barra de abas
        plus = QToolButton()
        plus.setIcon(icon("plus", 18))
        plus.setToolTip("Abrir PDF  (Ctrl+O)")
        plus.clicked.connect(self.open_dialog)
        plus.setFixedSize(32, 32)
        logo = QLabel()
        logo.setPixmap(brand_pixmap(22))
        logo.setFixedSize(22, 22)
        logo.setScaledContents(True)
        left = QWidget()
        left.setObjectName("titlecorner")
        left.setAttribute(Qt.WA_StyledBackground, True)
        lh = QHBoxLayout(left)
        lh.setContentsMargins(12, 4, 4, 0)
        lh.setSpacing(6)
        lh.addWidget(logo)
        lh.addWidget(plus)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_dialog)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.run_tool("create"))
        self.tabs.setCornerWidget(left, Qt.TopLeftCorner)

        right = QWidget()
        right.setObjectName("titlecorner")
        right.setAttribute(Qt.WA_StyledBackground, True)
        rh = QHBoxLayout(right)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(0)
        rh.addWidget(self._build_app_menu())
        rh.addSpacing(6)
        self.btn_min = WinButton("win_min", "Minimizar")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max = WinButton("win_max", "Maximizar")
        self.btn_max.clicked.connect(self._toggle_maximize)
        self.btn_close = WinButton("win_close", "Fechar")
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            rh.addWidget(b)
        self.tabs.setCornerWidget(right, Qt.TopRightCorner)
        self.tabs.tabBar().installEventFilter(self)       # arrastar a janela pela área vazia das abas
        QApplication.instance().installEventFilter(self)  # redimensionar pelas bordas
        self._edge_cursor = False
        self.refresh_recent()
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    # ---- barra de título própria (janela sem moldura) ------------------------------------------
    def _toggle_maximize(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange and hasattr(self, "btn_max"):
            maxed = self.isMaximized()
            self.btn_max.set_kind("win_restore" if maxed else "win_max")
            self.btn_max.setToolTip("Restaurar" if maxed else "Maximizar")

    def _edges_at(self, gp) -> Qt.Edges:
        r, m = self.frameGeometry(), self.RESIZE_MARGIN
        if not r.contains(gp):
            return Qt.Edges()
        edges = Qt.Edges()
        if gp.x() - r.left() < m:
            edges |= Qt.LeftEdge
        elif r.right() - gp.x() < m:
            edges |= Qt.RightEdge
        if gp.y() - r.top() < m:
            edges |= Qt.TopEdge
        elif r.bottom() - gp.y() < m:
            edges |= Qt.BottomEdge
        return edges

    def _set_edge_cursor(self, edges) -> None:
        shape = None
        if edges:
            horiz = bool(edges & (Qt.LeftEdge | Qt.RightEdge))
            vert = bool(edges & (Qt.TopEdge | Qt.BottomEdge))
            diag_back = (edges & Qt.LeftEdge and edges & Qt.TopEdge) or (edges & Qt.RightEdge and edges & Qt.BottomEdge)
            shape = (Qt.SizeFDiagCursor if diag_back else Qt.SizeBDiagCursor) if horiz and vert \
                else Qt.SizeHorCursor if horiz else Qt.SizeVerCursor
        if shape is not None and not self._edge_cursor:
            QApplication.setOverrideCursor(shape)
            self._edge_cursor = True
        elif shape is not None:
            QApplication.changeOverrideCursor(shape)
        elif self._edge_cursor:
            QApplication.restoreOverrideCursor()
            self._edge_cursor = False

    def eventFilter(self, obj, ev):  # noqa: N802
        t = ev.type()
        if obj is self.tabs.tabBar():
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton \
                    and self.tabs.tabBar().tabAt(ev.position().toPoint()) < 0:
                handle = self.windowHandle()
                if handle is not None and not self.isFullScreen():
                    handle.startSystemMove()
                    return True
            elif t == QEvent.MouseButtonDblClick and ev.button() == Qt.LeftButton \
                    and self.tabs.tabBar().tabAt(ev.position().toPoint()) < 0:
                self._toggle_maximize()
                return True
            return False
        if t in (QEvent.MouseMove, QEvent.MouseButtonPress) and isinstance(obj, QWidget) \
                and obj.window() is self and not self.isMaximized() and not self.isFullScreen():
            gp = ev.globalPosition().toPoint()
            edges = self._edges_at(gp)
            if t == QEvent.MouseMove:
                self._set_edge_cursor(edges)
            elif edges and ev.button() == Qt.LeftButton and self.windowHandle() is not None:
                self.windowHandle().startSystemResize(edges)
                return True
        elif t == QEvent.Leave and obj is self and self._edge_cursor:
            self._set_edge_cursor(Qt.Edges())
        return False

    def show_preferences(self) -> None:
        dlg = PreferencesDialog(ui_common.appearance_pref(), self.auto_update_enabled(), self)
        if dlg.exec():
            look, auto = dlg.values()
            self.settings.setValue("auto_update", "true" if auto else "false")
            if look != ui_common.appearance_pref():
                self.set_appearance(look)

    def _make_home(self) -> HomePage:
        home = HomePage()
        home.open_requested.connect(self.open_dialog)
        home.create_requested.connect(lambda: self.run_tool("create"))
        home.tool_requested.connect(self.run_tool)
        home.recent_requested.connect(self.open_path)
        home.remove_recent_requested.connect(self.remove_recent)
        home.clear_recent_requested.connect(self.clear_recent)
        home.about_requested.connect(self.show_about)
        return home

    def _focus_search(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.home.focus_search()

    def remove_recent(self, path: str) -> None:
        self.settings.setValue("recent", [p for p in self.recent() if p != path])
        self.refresh_recent()

    # ---- menu do aplicativo e aparência ---------------------------------------------
    def _build_app_menu(self) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon("menu", 20))
        btn.setToolTip("Menu")
        btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(btn)
        menu.addAction("Abrir PDF…", self.open_dialog)
        look = menu.addMenu("Aparência")
        group = QActionGroup(self)
        current = ui_common.appearance_pref()
        for label, key in (("Seguir o sistema", "system"), ("Claro", "light"), ("Escuro", "dark")):
            act = look.addAction(label)
            act.setCheckable(True)
            act.setChecked(key == current)
            act.triggered.connect(lambda _=False, k=key: self.set_appearance(k))
            group.addAction(act)
        menu.addSeparator()
        self.update_act = menu.addAction("Verificar atualizações…", self.check_updates)
        menu.addAction("Sobre o " + APP_NAME, self.show_about)
        btn.setMenu(menu)
        return btn

    def set_appearance(self, pref: str) -> None:
        self.settings.setValue("appearance", pref)
        QSettings("VerticePDF", "VerticePDF").setValue("appearance", pref)
        self.apply_appearance()

    def apply_appearance(self) -> None:
        app = QApplication.instance()
        apply_theme(app)
        current = self.tabs.currentIndex()
        self.tabs.removeTab(0)
        old, self.home = self.home, self._make_home()
        self.tabs.insertTab(0, self.home, QIcon(render("home", icons.ICON_COLOR, 36)), "Início")
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tabs.setCurrentIndex(current)
        old.deleteLater()
        self.refresh_recent()

    def _on_system_scheme(self, *_args) -> None:
        if ui_common.appearance_pref() == "system":
            self.apply_appearance()

    # ---- atualização do aplicativo ----------------------------------------------------
    def update_url(self) -> str:
        import os
        return (os.environ.get("VERTICE_UPDATE_URL") or str(self.settings.value("update_url", "") or "")
                or UPDATE_URL).strip()

    def check_updates(self, info: dict | None = None) -> None:
        url = self.update_url()
        if not url:
            QMessageBox.information(
                self, "Atualizações",
                "O endereço de atualização ainda não foi configurado nesta versão.\n\n"
                "Defina UPDATE_URL em version.py (ex.: a API de releases do seu repositório no GitHub) "
                "e gere o instalador novamente.")
            return
        dlg = UpdateDialog(__version__, url, self, info if isinstance(info, dict) else None)
        dlg.exec()
        if dlg.installer_path:
            self.install_update(dlg.installer_path)

    def install_update(self, installer_path: str) -> None:
        """Fecha o programa (perguntando se salva o que estiver aberto) e roda o instalador por cima."""
        if not self._confirm_all_tabs():
            QMessageBox.information(self, "Atualização", "Atualização adiada. O instalador foi baixado e verificado; "
                                    "use Verificar atualizações… quando quiser concluir.")
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self._updating = True
        updater.launch_installer(installer_path)
        QApplication.quit()

    def auto_update_enabled(self) -> bool:
        return str(self.settings.value("auto_update", "true")).lower() != "false"

    def auto_check_updates(self) -> None:
        """Uma vez por dia, em segundo plano: avisa discretamente se houver versão nova."""
        url = self.update_url()
        now = datetime.now().timestamp()
        if not url or not self.auto_update_enabled() or now - float(self.settings.value("last_update_check", 0) or 0) < 86400:
            return
        self.settings.setValue("last_update_check", now)

        def run(_prog):
            return updater.fetch_latest(url)

        def done(info):
            if updater.is_newer(info["version"], __version__):
                self._pending_update = info
                self.update_act.setText(f"Atualização disponível: {info['version']}…")
                self.update_act.triggered.disconnect()
                self.update_act.triggered.connect(lambda: self.check_updates(self._pending_update))
                self.statusBar().showMessage(f"Nova versão {info['version']} disponível — menu ≡ › Atualização disponível.", 12000)

        w = Worker(run, self)
        w.done.connect(done)
        w.failed.connect(lambda _m: None)      # sem internet / sem releases: silêncio
        self._update_worker = w
        w.start()

    # ---- recuperação de sessões interrompidas -------------------------------------
    def offer_recovery(self) -> None:
        items = recovery.pending()
        if not items:
            return
        names = "\n".join(f"  • {it['title']}" for it in items[:8])
        box = QMessageBox(QMessageBox.Question, "Recuperar documentos",
                          f"O {APP_NAME} foi encerrado antes de salvar {len(items)} documento(s):\n\n{names}\n\n"
                          "Deseja recuperar essas alterações?", parent=self)
        yes = box.addButton("Recuperar", QMessageBox.AcceptRole)
        no = box.addButton("Descartar", QMessageBox.DestructiveRole)
        box.exec()
        for it in items:
            if box.clickedButton() is yes:
                loaded = self.load_doc(it["pdf"])
                if loaded:
                    view = self.add_view(*loaded, path=None, title=f"{it['title']} (recuperado)")
                    view.suggest_path = it.get("original")
                    view.set_modified(True)
                    view.autosave()      # já protege a cópia sob o novo id antes de apagar a antiga
            if box.clickedButton() in (yes, no):
                recovery.discard(it["id"])

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_about(self) -> None:
        QMessageBox.about(
            self, f"Sobre o {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Editor de PDF para desktop feito com Python, PySide6 e PyMuPDF.</p>"
            "<p>PyMuPDF é distribuído sob AGPL-3.0 (Artifex). Se você redistribuir este "
            "programa, respeite os termos dessa licença.</p>"
            f"<p style='color:#888'>Log de erros:<br>{LOG_PATH}</p>")

    # ---- recentes -----------------------------------------------------------
    def recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        return [value] if isinstance(value, str) else list(value or [])

    def refresh_recent(self) -> None:
        self.home.set_recent(self.recent())

    def add_recent(self, path: str) -> None:
        paths = [p for p in self.recent() if p != path]
        paths.insert(0, path)
        self.settings.setValue("recent", paths[:MAX_RECENT])
        self.refresh_recent()

    def clear_recent(self) -> None:
        self.settings.setValue("recent", [])
        self.refresh_recent()

    # ---- abrir / fechar ------------------------------------------------------
    def open_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Abrir PDF", last_dir(), "PDF (*.pdf)")
        if paths:
            remember_dir(paths[0])
        for p in paths:
            self.open_path(p)

    def load_doc(self, path: str):
        """Abre um PDF (pedindo a senha se preciso). Retorna (doc, senha) ou None."""
        try:
            doc = fitz.open(stream=Path(path).read_bytes(), filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao abrir", f"Não foi possível abrir:\n{path}\n\n{exc}")
            return None
        password = None
        if doc.needs_pass:
            for _ in range(3):
                pw, ok = QInputDialog.getText(self, "PDF protegido", f"Senha de {Path(path).name}:",
                                              QLineEdit.Password)
                if not ok:
                    doc.close()
                    return None
                if doc.authenticate(pw):
                    password = pw
                    break
            else:
                doc.close()
                QMessageBox.warning(self, "PDF protegido", "Senha incorreta.")
                return None
        return doc, password

    def open_path(self, path: str) -> PdfView | None:
        path = str(Path(path))
        for i in range(1, self.tabs.count()):
            v = self.tabs.widget(i)
            if isinstance(v, PdfView) and v.path and Path(v.path) == Path(path):
                self.tabs.setCurrentIndex(i)
                return v
        loaded = self.load_doc(path)
        if not loaded:
            return None
        view = self.add_view(*loaded, path=path, title=Path(path).name)
        self.add_recent(path)
        return view

    def add_view(self, doc, password, path: str | None, title: str) -> PdfView:
        view = PdfView(doc, path, password)
        idx = self.tabs.addTab(view, title)
        close = QToolButton()
        close.setIcon(icon("close", 14))
        close.setToolTip("Fechar")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(lambda _=False, v=view: self.close_tab(self.tabs.indexOf(v)))
        self.tabs.tabBar().setTabButton(idx, QTabBar.RightSide, close)
        self.tabs.setCurrentIndex(idx)
        view.open_requested.connect(self.open_path)
        view.open_dialog_requested.connect(self.open_dialog)
        view.create_requested.connect(lambda: self.run_tool("create"))
        view.prefs_requested.connect(self.show_preferences)
        view.recent_provider = self.recent
        view.new_document.connect(self._new_document)
        view.title_changed.connect(lambda name, v=view: self._retitle(v, name))
        view.modified_changed.connect(lambda m, v=view: self._retitle(v, None))
        view._base_title = title
        return view

    def _new_document(self, data: bytes, name: str) -> None:
        view = self.add_view(fitz.open(stream=data, filetype="pdf"), None, None, name)
        view.set_modified(True)

    def _retitle(self, view: PdfView, name: str | None) -> None:
        if name:
            view._base_title = name
            self.add_recent(view.path)
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabText(i, ("● " if view.modified else "") + view._base_title)

    def close_tab(self, index: int) -> None:
        view = self.tabs.widget(index)
        if isinstance(view, PdfView):
            if not view.confirm_close():
                return
            self.tabs.removeTab(index)
            view.doc.close()
            view.deleteLater()

    def _confirm_all_tabs(self) -> bool:
        for i in range(self.tabs.count() - 1, 0, -1):
            view = self.tabs.widget(i)
            if isinstance(view, PdfView):
                self.tabs.setCurrentIndex(i)
                if not view.confirm_close():
                    return False
        return True

    def closeEvent(self, e):  # noqa: N802
        if not getattr(self, "_updating", False) and not self._confirm_all_tabs():
            e.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        e.accept()

    # ---- arrastar e soltar -----------------------------------------------------
    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self.drop.setGeometry(self.rect().adjusted(24, 24, -24, -24))

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.show()
            self.drop.raise_()

    def dragLeaveEvent(self, e):  # noqa: N802
        self.drop.hide()

    def dropEvent(self, e):  # noqa: N802
        self.drop.hide()
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf"):
                self.open_path(p)

    # ---- ferramentas -----------------------------------------------------------
    def pick_pdf(self, title: str = "Escolher PDF") -> str | None:
        path, _ = QFileDialog.getOpenFileName(self, title, last_dir(), "PDF (*.pdf)")
        remember_dir(path)
        return path or None

    def run_tool(self, key: str) -> None:
        if key == "create":
            dlg = CreateDialog(self)
            if dlg.exec() and dlg.data:
                doc = fitz.open(stream=dlg.data, filetype="pdf")
                view = self.add_view(doc, None, None, dlg.name)
                view.set_modified(True)
        elif key == "batch":
            BatchDialog(self, 0).exec()
        elif key == "compress":
            BatchDialog(self, 2).exec()
        elif key == "encrypt":
            EncryptDialog(self).exec()
        elif key == "ocr":
            dlg = OcrDialog(self)
            dlg.exec()
            if dlg.result_path:
                self.open_path(dlg.result_path)
        elif key == "organize":
            path = self.pick_pdf("Escolher PDF para organizar")
            loaded = self.load_doc(path) if path else None
            if loaded:
                dlg = OrganizeDialog(loaded[0], path, self)
                dlg.exec()
                if dlg.result_path:
                    self.open_path(dlg.result_path)
        elif key == "share":
            path = self.pick_pdf("Escolher PDF para compartilhar")
            if path:
                from PySide6.QtCore import QMimeData, QUrl
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(path)])
                QGuiApplication.clipboard().setMimeData(mime)
                QMessageBox.information(self, "Compartilhar PDF",
                                        "O arquivo foi copiado. Cole (Ctrl+V) em um e-mail, chat ou pasta para enviá-lo.")
        elif key in ("edit", "print", "form"):
            path = self.pick_pdf()
            view = self.open_path(path) if path else None
            if view:
                if key == "edit":
                    view.set_tool("edittext")
                elif key == "print":
                    view.print_doc()
                else:
                    view.fill_forms()


def setup_logging() -> None:
    global LOG_PATH
    folder = recovery.data_root()
    LOG_PATH = str(folder / "verticepdf.log")
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Vértice PDF %s iniciado", __version__)

    def hook(exc_type, exc, tb):
        logging.error("Erro não tratado:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        QMessageBox.critical(None, "Erro inesperado",
                             f"{exc}\n\nOs detalhes foram gravados em:\n{LOG_PATH}")

    sys.excepthook = hook


def selftest(report_path: str | None) -> int:
    """Teste de fumaça do programa já empacotado (usado pelo build e pelo CI).

    Uso:  VerticePDF.exe --selftest relatorio.txt
    """
    import tempfile

    lines: list[str] = []
    ok = True

    def step(name: str, fn) -> None:
        nonlocal ok
        try:
            res = fn()
            lines.append(f"OK    {name}" + (f"  ({res})" if res else ""))
        except Exception:  # noqa: BLE001
            ok = False
            lines.append(f"FALHA {name}\n{traceback.format_exc()}")

    app = QApplication(sys.argv[:1])
    apply_theme(app)
    tmp = Path(tempfile.mkdtemp(prefix="verticepdf_selftest_"))
    pdf = tmp / "t.pdf"

    def make_pdf():
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(72, 100, 320, 200), "Paragrafo de teste do Vertice para o autoteste.",
                            fontsize=12, fontname="helv")
        doc.save(pdf)
        return f"PyMuPDF {fitz.version[0]}"

    def window():
        win = MainWindow()
        view = PdfView(fitz.open(pdf), str(pdf))
        view.resize(900, 700)
        view.show()
        app.processEvents()
        assert view.labels and view.thumbs.count() == 1
        view.render_page(0)
        win.deleteLater()
        view.deleteLater()

    def engine():
        import annots
        import textedit
        merged = tmp / "m.pdf"
        ops.merge([str(pdf), str(pdf)], str(merged))
        ops.compress(str(merged), str(tmp / "c.pdf"), "media")
        ops.encrypt(str(pdf), str(tmp / "e.pdf"), "x")
        ops.decrypt(str(tmp / "e.pdf"), str(tmp / "d.pdf"), "x")
        page = ops.open_pdf(pdf)[0]
        block = textedit.block_at(page, (100, 105))
        assert block, "bloco de texto não encontrado"
        textedit.replace_block(page, block, "Texto editado")
        annots.add_line(page, (50, 300), (150, 340), (1, 0, 0), 2, True)
        annots.add_note(page, (300, 300), "ok")
        return f"{len(textedit.font_index())} fontes do sistema"

    def signature():
        import signing
        pfx = tmp / "c.pfx"
        signing.create_self_signed(str(pfx), "1234", "Autoteste")
        out = tmp / "s.pdf"
        signing.sign_pdf(pdf.read_bytes(), str(out), str(pfx), "1234", visible=True,
                         page_index=0, box=(300, 50, 520, 120))
        (r,) = signing.verify(out.read_bytes())
        assert r["intact"] and r["valid"], r

    def export():
        import zipfile
        import exporters
        doc = fitz.open(pdf)
        for name, fn in (("a.docx", exporters.export_docx), ("a.xlsx", exporters.export_xlsx),
                         ("a.pptx", exporters.export_pptx)):
            fn(doc, str(tmp / name))
            assert zipfile.is_zipfile(tmp / name), name
        assert len(exporters.export_images(doc, str(tmp / "a.png"), "png", 72)) == 1
        return "Word, Excel, PowerPoint e imagem"

    def ocr():
        exe = ops.find_tesseract()
        if not exe:
            return "Tesseract não encontrado (OCR indisponível)"
        pix = fitz.open(pdf)[0].get_pixmap(dpi=150)
        pix.save(tmp / "scan.png")
        (tmp / "scan.pdf").write_bytes(ops.images_to_pdf([str(tmp / "scan.png")]))
        ops.ocr_pdf(str(tmp / "scan.pdf"), str(tmp / "ocr.pdf"), "eng", 150)
        text = ops.open_pdf(tmp / "ocr.pdf")[0].get_text().lower()
        assert "teste" in text or "vertice" in text, f"OCR não reconheceu o texto: {text!r}"
        return Path(exe).parent.name

    step("motor de PDF", make_pdf)
    step("interface", window)
    step("edição, anotações e fontes", engine)
    step("assinatura digital", signature)
    step("exportação", export)
    step("OCR", ocr)
    lines.append("\nRESULTADO: " + ("TUDO OK" if ok else "COM FALHAS"))
    text = "\n".join(lines)
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if ok else 1


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"VerticePDF-{user}"


def forward_to_running(paths: list[str]) -> bool:
    """Se já houver uma janela aberta, entrega os arquivos a ela e devolve True."""
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(500):
        return False
    sock.write(json.dumps(paths).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1500)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Mantém uma única janela: abrir outro PDF no Explorer vira uma nova aba nela."""
    files = Signal(list)

    def __init__(self):
        super().__init__()
        self.server = QLocalServer(self)
        QLocalServer.removeServer(_server_name())   # sobra de uma sessão que travou
        self.ok = self.server.listen(_server_name())
        self.server.newConnection.connect(self._accept)

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.setParent(self)          # o socket morre junto com o servidor (sem sinais soltos)
            sock.setProperty("buf", b"")
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._done(s))

    @staticmethod
    def _read(sock) -> None:
        sock.setProperty("buf", bytes(sock.property("buf") or b"") + bytes(sock.readAll()))

    def _done(self, sock) -> None:
        self._read(sock)
        try:
            paths = [p for p in json.loads(bytes(sock.property("buf")).decode("utf-8")) if isinstance(p, str)]
        except ValueError:
            paths = []
        sock.deleteLater()
        self.files.emit(paths)


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        return selftest(sys.argv[2] if len(sys.argv) > 2 else None)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VerticePDF")
    paths = [str(Path(a).resolve()) for a in sys.argv[1:] if a.lower().endswith(".pdf") and Path(a).is_file()]
    if forward_to_running(paths):
        return 0
    setup_logging()
    apply_theme(app)
    win = MainWindow()
    win.show()
    instance = InstanceServer()
    try:                                   # acompanha o tema do Windows quando está em "Seguir o sistema"
        QGuiApplication.styleHints().colorSchemeChanged.connect(win._on_system_scheme)
    except Exception:  # noqa: BLE001
        pass

    def open_files(files: list) -> None:
        for f in files:
            if f.lower().endswith(".pdf") and Path(f).is_file():
                win.open_path(f)
        win.bring_to_front()

    instance.files.connect(open_files)
    for arg in paths:
        win.open_path(arg)
    QTimer.singleShot(400, win, win.offer_recovery)
    QTimer.singleShot(4000, win, win.auto_check_updates)
    code = app.exec()
    del instance
    return code


if __name__ == "__main__":
    sys.exit(main())
