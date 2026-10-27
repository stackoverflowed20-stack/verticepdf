"""Visualizador / editor de PDF (uma aba por documento)."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QSizePolicy, QStackedWidget, QTabBar, QColorDialog, QDialog, QFileDialog, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QScrollArea, QSpinBox, QSplitter,
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QPushButton, QTabWidget, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

import annots
import ops
import pagetools
import recovery
import signing
import textedit
from dialogs import (BatchDialog, CreateDialog, CropDialog, EncryptDialog, ExtractDialog, FindReplaceDialog,
                     HeaderFooterDialog, OcrDialog, OrganizeDialog, STAMPS, WatermarkDialog, CertSignDialog, FormDialog, ParagraphEditDialog, SignatureDialog,
                     make_stamp_png, show_verification)
from icons import color_dot, icon
from ui_common import ACCENT, Toast, last_dir, remember_dir

TOOL_INFO = {
    "select": ("Selecionar", "Arraste para selecionar texto (inclusive entre páginas). Ctrl+C copia, Ctrl+A seleciona tudo."),
    "edittext": ("Editar texto", "Clique em uma palavra para trocar só ela (o parágrafo aparece emoldurado). Use \"¶\" na barra para editar o bloco todo."),
    "addtext": ("Adicionar texto", "Clique no ponto da página onde o texto deve aparecer."),
    "highlight": ("Realçar", "Arraste sobre o texto para realçá-lo."),
    "erase": ("Apagar área", "Arraste para apagar uma área (ela recebe a cor do fundo)."),
    "sign": ("Assinatura desenhada", "Arraste para definir o tamanho da assinatura, ou apenas clique."),
    "arrow": ("Seta", "Arraste do início até a ponta da seta."),
    "line": ("Linha", "Arraste para traçar a linha."),
    "rect": ("Retângulo", "Arraste para desenhar o retângulo."),
    "ellipse": ("Elipse", "Arraste para desenhar a elipse."),
    "ink": ("Caneta", "Mantenha o botão pressionado e desenhe à mão livre."),
    "note": ("Nota", "Clique onde a nota deve ficar. Botão direito sobre ela: editar ou excluir."),
    "freetext": ("Caixa de texto", "Arraste para definir a caixa e digite o texto."),
    "stamp": ("Carimbo", "Clique (ou arraste) para posicionar o carimbo."),
    "image": ("Adicionar imagem", "Arraste para definir o tamanho da imagem, ou apenas clique."),
}
TOOL_PROPS = {
    "addtext": ("size", "tcolor"), "freetext": ("size", "acolor"),
    "arrow": ("acolor", "width"), "line": ("acolor", "width"), "ink": ("acolor", "width"),
    "rect": ("acolor", "width", "fill"), "ellipse": ("acolor", "width", "fill"),
    "sign": ("sign",), "stamp": ("stamp",), "image": ("imgpick",),
}
ANNOT_TOOLS = {"arrow", "line", "rect", "ellipse", "ink", "note", "freetext"}
RECT_TOOLS = {"highlight", "erase", "sign", "image", "rect", "ellipse", "freetext", "stamp"}
LINE_TOOLS = {"line", "arrow"}
CLICK_TOOLS = {"addtext", "edittext", "note"}
DEFAULT_SIZE = {"sign": (150, 60), "image": (200, 150), "stamp": (160, 56), "freetext": (170, 50)}  # clique sem arrastar


def flat_icon(pm: QPixmap) -> QIcon:
    """Ícone sem o tingimento padrão de item selecionado."""
    ic = QIcon()
    for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected):
        ic.addPixmap(pm, mode)
    return ic


def pix_to_qpixmap(pix: "fitz.Pixmap") -> QPixmap:
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    return QPixmap.fromImage(img)  # fromImage copia os dados


# --------------------------------------------------------------------------
class PageLabel(QLabel):
    """Uma página renderizada + camada de interação (seleção, anotações, buscas)."""

    clicked = Signal(int, QPointF)
    area = Signal(int, QRectF)
    line = Signal(int, QPointF, QPointF)
    ink = Signal(int, list)
    sel_press = Signal(int)
    hovered = Signal(int, object)      # índice, QPointF em pontos (ou None ao sair)

    def __init__(self, index: int):
        super().__init__()
        self.index = index
        self.zoom = 1.0
        self.rendered = False
        self.mode = "select"
        self.hits: list[QRectF] = []
        self.cur_hit: QRectF | None = None
        self.get_words = None                      # callback: índice -> [(QRectF, texto, (bloco, linha))]
        self.sel: tuple[int, int] | None = None    # intervalo de palavras selecionadas (definido pelo PdfView)
        self.preview_color = QColor(ACCENT)
        self._start: QPointF | None = None
        self._cur: QPointF | None = None
        self._stroke: list[QPointF] = []
        self.para_hover: QRectF | None = None      # moldura tracejada (passar o mouse)
        self.para_sel: QRectF | None = None        # parágrafo selecionado (moldura + alças)
        self.word_sel: QRectF | None = None        # palavra que será trocada
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setObjectName("pagelabel")
        self.setStyleSheet("QLabel#pagelabel { background: white; }")

    def paintEvent(self, e):  # noqa: N802
        super().paintEvent(e)
        z = self.zoom
        p = QPainter(self)

        def box(r: QRectF) -> QRectF:
            return QRectF(r.x() * z, r.y() * z, r.width() * z, r.height() * z)

        for r in self.hits:
            p.fillRect(box(r), QColor(255, 230, 0, 120))
        if self.cur_hit is not None:
            p.fillRect(box(self.cur_hit), QColor(255, 140, 0, 160))
        if self.sel is not None and self.get_words:
            a, b = self.sel
            for r, _t, _ln in self.get_words(self.index)[a:b + 1]:
                p.fillRect(box(r), QColor(60, 130, 255, 90))
        if self.word_sel is not None:
            wr = box(self.word_sel)
            p.fillRect(wr, QColor(31, 95, 209, 70))
            p.setPen(QPen(QColor(ACCENT), 1))
            p.drawRect(wr)
        if self.para_hover is not None and self.para_hover != self.para_sel:
            p.setPen(QPen(QColor(ACCENT), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(box(self.para_hover).adjusted(-3, -3, 3, 3))
        if self.para_sel is not None:
            fr = box(self.para_sel).adjusted(-3, -3, 3, 3)
            p.setPen(QPen(QColor(ACCENT), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRect(fr)
            p.setBrush(QColor("white"))
            cx, cy = fr.center().x(), fr.center().y()
            for hx, hy in ((fr.left(), fr.top()), (cx, fr.top()), (fr.right(), fr.top()),
                           (fr.left(), cy), (fr.right(), cy),
                           (fr.left(), fr.bottom()), (cx, fr.bottom()), (fr.right(), fr.bottom())):
                p.drawRect(QRectF(hx - 3.5, hy - 3.5, 7, 7))
        pen = QPen(self.preview_color, 1.5, Qt.DashLine)
        p.setPen(pen)
        if self._start is not None and self._cur is not None:
            if self.mode in RECT_TOOLS:
                p.setBrush(QColor(232, 69, 60, 35))
                p.drawRect(QRectF(self._start, self._cur).normalized())
            elif self.mode in LINE_TOOLS:
                p.drawLine(self._start, self._cur)
        if len(self._stroke) > 1:
            p.setPen(QPen(self.preview_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for a, b in zip(self._stroke, self._stroke[1:]):
                p.drawLine(a, b)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        if self.mode == "select":
            self.sel_press.emit(self.index)
        elif self.mode == "ink":
            self._stroke = [e.position()]
        else:
            self._start = self._cur = e.position()

    def leaveEvent(self, e):  # noqa: N802
        if self.mode == "edittext":
            self.hovered.emit(self.index, None)
        super().leaveEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self.mode == "edittext" and not e.buttons():
            z = self.zoom
            self.hovered.emit(self.index, QPointF(e.position().x() / z, e.position().y() / z))
        elif self.mode == "ink" and self._stroke:
            self._stroke.append(e.position())
            self.update()
        elif self._start is not None and self.mode in RECT_TOOLS | LINE_TOOLS:
            self._cur = e.position()
            self.update()

    def mouseReleaseEvent(self, e):  # noqa: N802
        z = self.zoom
        if self.mode == "ink" and self._stroke:
            pts = [QPointF(q.x() / z, q.y() / z) for q in self._stroke]
            self._stroke = []
            self.update()
            if len(pts) > 2:
                self.ink.emit(self.index, pts)
            return
        if self._start is None:
            return
        a, b = self._start, e.position()
        self._start = self._cur = None
        self.update()
        dist = abs(a.x() - b.x()) + abs(a.y() - b.y())
        dragged = abs(a.x() - b.x()) > 4 and abs(a.y() - b.y()) > 4
        if self.mode in LINE_TOOLS:
            if dist > 8:
                self.line.emit(self.index, QPointF(a.x() / z, a.y() / z), QPointF(b.x() / z, b.y() / z))
        elif self.mode in RECT_TOOLS and dragged:
            self.area.emit(self.index, QRectF(QPointF(a.x() / z, a.y() / z),
                                              QPointF(b.x() / z, b.y() / z)).normalized())
        elif self.mode in DEFAULT_SIZE:  # clique simples: tamanho padrão centrado no clique
            w, h = DEFAULT_SIZE[self.mode]
            self.area.emit(self.index, QRectF(b.x() / z - w / 2, b.y() / z - h / 2, w, h))
        elif self.mode in CLICK_TOOLS:
            self.clicked.emit(self.index, QPointF(b.x() / z, b.y() / z))


# --------------------------------------------------------------------------
class PdfView(QWidget):
    modified_changed = Signal(bool)
    title_changed = Signal(str)
    open_requested = Signal(str)
    new_document = Signal(bytes, str)

    signature_png: bytes | None = None  # compartilhada entre abas

    def __init__(self, doc: "fitz.Document", path: str | None, password: str | None = None,
                 parent=None):
        super().__init__(parent)
        self.doc = doc
        self.path = path
        self.password = password
        self.modified = False
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []
        self.rid = uuid.uuid4().hex
        self.zoom = 1.25
        self.tool = "select"
        self.labels: list[PageLabel] = []
        self.sizes: list[tuple[float, float]] = []
        self.hits: list[tuple[int, QRectF]] = []
        self.hit_i = -1
        self._query = ""
        self._first_show = True
        self._sync = False
        self.text_color = QColor("#000000")
        self.sel_text = ""
        self._sel_anchor: tuple[int, int] | None = None
        self._sel_cur: tuple[int, int] | None = None
        self._sel_active = False
        self._sel_origin = None
        self._sel_timer = QTimer(self)
        self._sel_timer.setInterval(30)
        self._sel_timer.timeout.connect(self._sel_tick)
        self.ann_color = QColor("#e53935")
        self.stamp_spec: tuple[str, str] = STAMPS[0]
        self.image_png: bytes | None = None
        sf = doc.get_sigflags()
        self.is_signed = sf > 0 and bool(sf & 1)
        self._signed_ok = False
        self._words_cache: dict[int, list] = {}
        self._thumb_gen = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tool_actions: dict[str, QAction] = {}
        self._group = QActionGroup(self)
        self._build_stamp_menu()
        self._build_topbar(root)
        self._build_propbar(root)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container.setObjectName("pages")
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(28, 28, 28, 28)
        self.vbox.setSpacing(18)
        self.scroll.setWidget(self.container)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.scroll.viewport().installEventFilter(self)

        self._build_panel()
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.panel)
        self.splitter.addWidget(self.scroll)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([230, 1000])
        self.splitter.setStretchFactor(1, 1)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.splitter, 1)
        root.addLayout(body, 1)

        copy = QAction(self)
        copy.setShortcut(QKeySequence.Copy)
        copy.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        copy.triggered.connect(self.copy_selection)
        self.addAction(copy)
        select_all = QAction(self)
        select_all.setShortcut(QKeySequence.SelectAll)
        select_all.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        select_all.triggered.connect(self.select_all_text)
        self.addAction(select_all)

        self._build_statusbar(root)
        self.toast = Toast(self)

        self.build_pages()
        self.fill_panel()
        self.set_tool("select")
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(45_000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()
        if self.is_signed:
            self.hint.setText("🔏 Documento assinado digitalmente — use “Verificar assinaturas”. "
                              "Editar e salvar invalida as assinaturas.")

    # ---- barras de ferramentas ------------------------------------------
    def _act(self, tb: QToolBar, text: str, slot, shortcut=None, tip: str = "",
             checkable: bool = False, icon_name: str | None = None) -> QAction:
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        a.setCheckable(checkable)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        if tip or text:
            base = tip or text
            a.setToolTip(base + (f"  ({QKeySequence(shortcut).toString()})" if shortcut else ""))
        a.triggered.connect(slot)
        tb.addAction(a)
        self.addAction(a)
        return a

    @staticmethod
    def _toolbar() -> QToolBar:
        tb = QToolBar()
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.setMovable(False)
        return tb

    def _bar(self, name: str) -> tuple[QWidget, QHBoxLayout]:
        w = QWidget()
        w.setObjectName(name)
        w.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(8)
        return w, h

    def _build_stamp_menu(self) -> None:
        menu = QMenu(self)
        for text, color in STAMPS:
            menu.addAction(text, lambda _=False, t=text, c=color: self.use_stamp(t, c))
        menu.addAction("Data de hoje", lambda _=False: self.use_stamp(datetime.now().strftime("%d/%m/%Y"), "#1565c0"))
        menu.addSeparator()
        menu.addAction("Personalizado…", self.custom_stamp)
        self.stamp_menu = menu

    TABS = ("Visualizar", "Editar", "Converter", "Anotar", "Página", "Proteger")

    def _build_topbar(self, root: QVBoxLayout) -> None:
        bar, h = self._bar("topbar")
        root.addWidget(bar)

        left = self._toolbar()
        h.addWidget(left)
        self.panel_act = self._act(left, "", self.toggle_panel, "F4",
                                   "Painel de miniaturas e marcadores", True, "panel")
        self.panel_act.setChecked(True)

        # Salvar: botão dividido (Salvar / Salvar como…)
        self.save_act = QAction(icon("save"), "Salvar", self)
        self.save_act.setShortcut(QKeySequence("Ctrl+S"))
        self.save_act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.save_act.setToolTip("Salvar  (Ctrl+S)")
        self.save_act.triggered.connect(self.save)
        self.addAction(self.save_act)
        save_as = QAction("Salvar como…", self)
        save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        save_as.triggered.connect(self.save_as)
        self.addAction(save_as)
        save_menu = QMenu(self)
        save_menu.addAction(save_as)
        save_btn = QToolButton()
        save_btn.setDefaultAction(self.save_act)
        save_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        save_btn.setMenu(save_menu)
        save_btn.setPopupMode(QToolButton.MenuButtonPopup)
        h.addWidget(save_btn)

        mid = self._toolbar()
        h.addWidget(mid)
        self.undo_act = self._act(mid, "", self.do_undo, "Ctrl+Z", "Desfazer última edição", False, "undo")
        self.undo_act.setEnabled(False)
        self.redo_act = self._act(mid, "", self.do_redo, "Ctrl+Y", "Refazer  (Ctrl+Y / Ctrl+Shift+Z)", False, "redo")
        self.redo_act.setEnabled(False)
        alt = QAction(self)
        alt.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        alt.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        alt.triggered.connect(self.do_redo)
        self.addAction(alt)
        self._act(mid, "", self.print_doc, "Ctrl+P", "Imprimir", False, "print")
        mid.setMinimumWidth(mid.sizeHint().width() + 4)   # nunca esconde desfazer/refazer/imprimir

        h.addStretch(1)
        self.ribbon_tabs = QTabBar()
        self.ribbon_tabs.setObjectName("ribbontabs")
        self.ribbon_tabs.setDrawBase(False)
        self.ribbon_tabs.setExpanding(False)
        self.ribbon_tabs.setUsesScrollButtons(False)
        self.ribbon_tabs.setCursor(Qt.PointingHandCursor)
        for t in self.TABS:
            self.ribbon_tabs.addTab(t)
        h.addWidget(self.ribbon_tabs)
        h.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar no documento")
        self.search.setFixedWidth(150)
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", 16, "#8794a7"), QLineEdit.LeadingPosition)
        self.search.returnPressed.connect(self.find_next)
        h.addWidget(self.search)
        self.search_lbl = QLabel("")
        self.search_lbl.setObjectName("dim")
        h.addWidget(self.search_lbl)
        focus = QAction(self)
        focus.setShortcut(QKeySequence("Ctrl+F"))
        focus.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        focus.triggered.connect(lambda: (self.search.setFocus(), self.search.selectAll()))
        self.addAction(focus)
        repl = QAction(self)
        repl.setShortcut(QKeySequence("Ctrl+H"))
        repl.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        repl.triggered.connect(self.find_replace)
        self.addAction(repl)
        self._build_ribbon(root)

    # ---- faixa de opções (uma aba por assunto) ----------------------------------
    def _build_ribbon(self, root: QVBoxLayout) -> None:
        wrap = QWidget()
        wrap.setObjectName("ribbon")
        wrap.setAttribute(Qt.WA_StyledBackground, True)
        wrap.setFixedHeight(58)
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        self.ribbon_stack = QStackedWidget()
        self.ribbon_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)   # não impõe largura mínima à janela
        wl.addWidget(self.ribbon_stack)
        root.addWidget(wrap)

        self._rib_pages: list[tuple[QHBoxLayout, list]] = []

        def page() -> QHBoxLayout:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(12, 5, 12, 5)
            lay.setSpacing(2)
            lay.addStretch(1)
            self.ribbon_stack.addWidget(w)
            self._rib_pages.append((lay, []))
            return lay

        def sep(lay: QHBoxLayout) -> None:
            f = QFrame()
            f.setObjectName("ribsep")
            f.setFixedSize(1, 26)
            lay.addSpacing(6)
            lay.addWidget(f)
            lay.addSpacing(6)

        def btn(lay, text, icon_name, slot=None, *, tool=None, menu=None, tip="", name=None):
            act = QAction(icon(icon_name, 20), text, self)
            act.setToolTip(tip or text)
            if tool:
                act.setCheckable(True)
                act.triggered.connect(lambda _=False, k=tool: self.set_tool(k))
                self._group.addAction(act)
                self.tool_actions[tool] = act
            elif slot:
                act.triggered.connect(slot)
            b = QToolButton()
            b.setObjectName("rb")
            b.setDefaultAction(act)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if text else Qt.ToolButtonIconOnly)
            b.setIconSize(QSize(20, 20))
            if menu is not None:
                b.setMenu(menu)
                b.setPopupMode(QToolButton.InstantPopup)
            lay.addWidget(b)
            if text:
                for L, bl in self._rib_pages:
                    if L is lay:
                        bl.append((b, text))
            if name:
                setattr(self, name, act)
            return act

        # Visualizar
        v = page()
        btn(v, "Selecionar", "select", tool="select", tip="Selecionar texto")
        sep(v)
        btn(v, "", "zoom_out", lambda: self.set_zoom(self.zoom / 1.2), tip="Diminuir zoom  (Ctrl+-)")
        btn(v, "", "zoom_in", lambda: self.set_zoom(self.zoom * 1.2), tip="Aumentar zoom  (Ctrl+=)")
        btn(v, "Ajustar à largura", "fit", self.fit_width, tip="Ajustar à largura  (Ctrl+0)")
        sep(v)
        btn(v, "", "prev", lambda: self.go_to_page(self.current_page() - 1), tip="Página anterior")
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, max(1, self.doc.page_count))
        self.page_spin.setFixedWidth(64)
        self.page_spin.valueChanged.connect(self._spin_changed)
        v.addWidget(self.page_spin)
        self.page_total = QLabel(f"  de {self.doc.page_count}  ")
        self.page_total.setObjectName("dim")
        v.addWidget(self.page_total)
        btn(v, "", "next", lambda: self.go_to_page(self.current_page() + 1), tip="Próxima página")
        v.addStretch(1)

        # Editar
        e = page()
        btn(e, "Editar texto", "edit", tool="edittext", tip="Editar texto (palavra ou parágrafo)")
        btn(e, "Adicionar texto", "text", tool="addtext")
        btn(e, "Adicionar imagem", "image", tool="image")
        btn(e, "Apagar área", "erase", tool="erase")
        btn(e, "Assinatura", "sign", tool="sign", tip="Assinatura desenhada")
        sep(e)
        btn(e, "Localizar e substituir", "replace", self.find_replace, tip="Localizar e substituir texto  (Ctrl+H)")
        btn(e, "Marca d'água", "watermark", self.watermark)
        btn(e, "Cabeçalho e rodapé", "headfoot", lambda: self.header_footer("header"))
        btn(e, "Nº de página", "hash", lambda: self.header_footer("number"), tip="Numerar páginas")
        sep(e)
        btn(e, "OCR", "scan", lambda: self._dialog("ocr"), tip="Reconhecer texto (OCR)")
        btn(e, "Comprimir", "compress", lambda: self._dialog("compress"))
        btn(e, "Formulário", "form", self.fill_forms, tip="Preencher formulário")
        e.addStretch(1)

        # Converter
        c = page()
        btn(c, "Para imagem", "to_image", lambda: self._dialog("convert"), tip="Converter em imagens PNG/JPG")
        btn(c, "Para texto", "to_text", lambda: self._dialog("convert"), tip="Extrair o texto (TXT)")
        sep(c)
        btn(c, "Imagem para PDF", "image", lambda: self._dialog("create"), tip="Criar PDF a partir de imagens")
        btn(c, "Novo PDF em branco", "blank", lambda: self._dialog("create"))
        sep(c)
        btn(c, "Processamento em lote", "layers", lambda: self._dialog("batch"))
        c.addStretch(1)

        # Anotar
        a = page()
        btn(a, "Realçar", "highlight", tool="highlight")
        btn(a, "Seta", "arrow", tool="arrow")
        btn(a, "Linha", "segment", tool="line")
        btn(a, "Retângulo", "rect", tool="rect")
        btn(a, "Elipse", "ellipse", tool="ellipse")
        btn(a, "Caneta", "ink", tool="ink", tip="Caneta (mão livre)")
        sep(a)
        btn(a, "Nota", "note", tool="note", tip="Nota / comentário")
        btn(a, "Caixa de texto", "freetext", tool="freetext")
        stamp = btn(a, "Carimbo", "stamp", menu=self.stamp_menu)
        stamp.setCheckable(True)
        self._group.addAction(stamp)
        self.tool_actions["stamp"] = stamp
        a.addStretch(1)

        # Página
        p = page()
        btn(p, "Organizar", "pages", lambda: self._dialog("organize"), tip="Reordenar, duplicar e excluir páginas")
        btn(p, "Girar à esquerda", "rotate_l", lambda: self._rotate_page(-90))
        btn(p, "Girar à direita", "rotate_r", lambda: self._rotate_page(90))
        btn(p, "Inserir em branco", "blank", self._insert_blank)
        btn(p, "Excluir página", "trash", self._delete_page)
        btn(p, "Recortar", "crop", self.crop_page, tip="Recortar as margens da página")
        sep(p)
        btn(p, "Extrair", "extract", self.extract_pages, tip="Extrair páginas para um novo PDF")
        btn(p, "Inserir PDF", "plus", self.insert_pdf, tip="Inserir páginas de outro PDF após a página atual")
        btn(p, "Dividir", "split", lambda: self._dialog("split"))
        btn(p, "Mesclar", "merge", lambda: self._dialog("merge"))
        p.addStretch(1)

        # Proteger
        r = page()
        btn(r, "Criptografar", "lock", lambda: self._dialog("encrypt"), tip="Proteger com senha")
        btn(r, "Descriptografar", "unlock", lambda: self._dialog("decrypt"), tip="Remover a senha")
        sep(r)
        btn(r, "Limpar metadados", "broom", self.clean_metadata, tip="Remover autor, título, datas e XMP do arquivo")
        sep(r)
        btn(r, "Assinar digitalmente", "cert", self.sign_digital, tip="Assinar com certificado digital")
        btn(r, "Verificar assinaturas", "verify", self.verify_signatures)
        r.addStretch(1)

        self.tool_actions["select"].setChecked(True)
        self.ribbon_tabs.currentChanged.connect(self.ribbon_stack.setCurrentIndex)

    def _fit_ribbon(self) -> None:
        """Em janelas estreitas, a faixa mostra só os ícones (o nome vira dica)."""
        if not getattr(self, "_rib_pages", None):
            return
        avail = self.width() - 8
        for lay, buttons in self._rib_pages:
            for b, _t in buttons:
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            lay.invalidate()
            lay.activate()
            if lay.sizeHint().width() > avail:
                for b, _t in buttons:
                    b.setToolButtonStyle(Qt.ToolButtonIconOnly)

    # ---- diálogos acionados pela faixa -----------------------------------------
    def _saved_path(self) -> str | None:
        """Caminho do arquivo no disco, salvando antes se houver alterações."""
        if self.modified or not self.path:
            if QMessageBox.question(self, "Salvar antes de continuar",
                                    "Esta ferramenta trabalha no arquivo salvo. Salvar o documento agora?"
                                    ) != QMessageBox.Yes or not self.save():
                return None
        return self.path

    def _dialog(self, key: str) -> None:
        if key in ("create",):
            dlg = CreateDialog(self)
            if dlg.exec() and dlg.data:
                self.new_document.emit(dlg.data, dlg.name)
            return
        path = None if key in ("batch",) else self._saved_path()
        if key != "batch" and not path:
            return
        if key == "ocr":
            dlg = OcrDialog(self)
            dlg.file.setText(path)
            dlg.exec()
            if dlg.result_path:
                self.open_requested.emit(dlg.result_path)
        elif key in ("encrypt", "decrypt"):
            dlg = EncryptDialog(self)
            dlg.file.setText(path)
            if key == "decrypt":
                dlg.r_remove.setChecked(True)
            dlg.exec()
        elif key == "organize":
            doc = fitz.open(path, filetype="pdf") if not self.password else None
            if doc is None:
                QMessageBox.information(self, "Organizar", "Remova a senha do PDF antes de organizar as páginas.")
                return
            dlg = OrganizeDialog(doc, path, self)
            dlg.exec()
            if dlg.result_path:
                self.open_requested.emit(dlg.result_path)
        else:  # lote: combinar, dividir, comprimir, converter
            tab = {"merge": 0, "split": 1, "compress": 2, "convert": 3, "batch": 0}[key]
            dlg = BatchDialog(self, tab)
            if path:
                target = {"merge": dlg.m_files, "split": dlg.s_file,
                          "compress": dlg.c_files, "convert": dlg.v_files}.get(key)
                if target is not None:
                    target.add_files([path])
            dlg.exec()

    # ---- ações de página (estruturais) -----------------------------------------
    def _structural(self, action, goto: int | None = None) -> None:
        if not self._confirm_signed():
            return
        self._push_undo()
        try:
            action()
        except Exception as exc:  # noqa: BLE001
            self._abort_edit()
            QMessageBox.warning(self, "Não foi possível aplicar", str(exc))
            return
        self.__dict__.pop("_para_cache", None)
        self._words_cache.clear()
        self.clear_search()
        self.close_word_editor()
        self.set_modified(True)
        self.build_pages()
        self.fill_panel()
        self.page_spin.setRange(1, max(1, self.doc.page_count))
        self.page_total.setText(f"  de {self.doc.page_count}  ")
        QTimer.singleShot(0, self, self.render_visible)
        if goto is not None:
            QTimer.singleShot(30, self, lambda: self.go_to_page(min(goto, self.doc.page_count - 1)))

    # ---- ferramentas de página e texto ----------------------------------------------
    def find_replace(self) -> None:
        sel = self.sel_text.strip() if self.sel_text and "\n" not in self.sel_text.strip() else ""
        dlg = FindReplaceDialog(self, sel)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if not v["query"].strip():
            return
        result = {}

        def run():
            self.setCursor(Qt.WaitCursor)
            try:
                result.update(textedit.replace_all(self.doc, v["query"], v["repl"], v["case"]))
            finally:
                self.unsetCursor()
            if not result["count"]:
                raise ValueError("Nenhuma ocorrência encontrada" + (
                    f" ({result['skipped']} não cabiam e foram puladas)." if result["skipped"] else "."))

        before = self.modified
        self._push_undo()
        try:
            run()
        except ValueError as exc:
            self._abort_edit()
            self.set_modified(before)
            QMessageBox.information(self, "Localizar e substituir", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._abort_edit()
            QMessageBox.warning(self, "Não foi possível aplicar", str(exc))
            return
        self._refresh_all()
        msg = f"{result['count']} substituição(ões) em {result['pages']} página(s)."
        if result["skipped"]:
            msg += f" {result['skipped']} não coube(ram) e foi(ram) pulada(s)."
        self.hint.setText(msg)
        self.notify(msg)

    def _refresh_all(self) -> None:
        self.__dict__.pop("_para_cache", None)
        self._words_cache.clear()
        self.clear_search()
        self.close_word_editor()
        self.set_modified(True)
        for lb in self.labels:
            lb.rendered = False
            lb.clear()
        self.render_visible()
        self.fill_panel()

    def _apply_pagetool(self, dlg_cls, func, ok_msg: str, *args) -> None:
        if not self._confirm_signed():
            return
        dlg = dlg_cls(*args, self)
        if dlg.exec() != QDialog.Accepted:
            return
        values = dlg.values()
        self._push_undo()
        try:
            n = func(values)
        except Exception as exc:  # noqa: BLE001
            self._abort_edit()
            QMessageBox.warning(self, "Não foi possível aplicar", str(exc))
            return
        self._refresh_all()
        self.notify(ok_msg.format(n=n))

    def watermark(self) -> None:
        self._apply_pagetool(WatermarkDialog, lambda v: pagetools.add_watermark(
            self.doc, v["text"], size=v["size"], color=v["color"], opacity=v["opacity"], angle=v["angle"],
            pages=v["pages"], behind=v["behind"]), "Marca d'água aplicada em {n} página(s).", self.doc.page_count)

    def header_footer(self, preset: str = "header") -> None:
        name = Path(self.path).name if self.path else ""
        self._apply_pagetool(HeaderFooterDialog, lambda v: pagetools.add_header_footer(
            self.doc, v["texts"], size=v["size"], color=v["color"], margin=v["margin"], pages=v["pages"],
            start=v["start"], filename=name), "Aplicado em {n} página(s).", self.doc.page_count, preset)

    def crop_page(self) -> None:
        cur = self.current_page() + 1
        self._apply_pagetool(CropDialog, lambda v: pagetools.crop_pages(
            self.doc, v["top"], v["right"], v["bottom"], v["left"], v["pages"]),
            "{n} página(s) recortada(s).", self.doc.page_count, cur)

    def extract_pages(self) -> None:
        dlg = ExtractDialog(self.doc.page_count, self.current_page() + 1, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            data = pagetools.extract_pages(self.doc, dlg.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Extrair páginas", str(exc))
            return
        base = Path(self.path).stem if self.path else "documento"
        out, _ = QFileDialog.getSaveFileName(self, "Salvar páginas extraídas",
                                             str(Path(last_dir()) / f"{base}_extraido.pdf"), "PDF (*.pdf)")
        if not out:
            return
        remember_dir(out)
        ops.write_file(out, data)
        self.notify(f"Páginas extraídas: {Path(out).name}")
        self.open_requested.emit(out)

    def insert_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Inserir páginas de…", last_dir(), "PDF (*.pdf)")
        if not path:
            return
        remember_dir(path)
        i = self.current_page()
        pw = None
        try:
            if fitz.open(path).needs_pass:
                pw, ok = QInputDialog.getText(self, "PDF protegido", "Senha do PDF a inserir:", QLineEdit.Password)
                if not ok:
                    return
            self._structural(lambda: pagetools.insert_pdf(self.doc, path, i, pw), i + 1)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Inserir PDF", str(exc))

    def clean_metadata(self) -> None:
        self._structural(lambda: pagetools.strip_metadata(self.doc), self.current_page())
        self.notify("Metadados removidos (valem ao salvar).")

    def _rotate_page(self, delta: int) -> None:
        i = self.current_page()
        self._structural(lambda: self.doc[i].set_rotation((self.doc[i].rotation + delta) % 360), i)

    def _insert_blank(self) -> None:
        i = self.current_page()
        r = self.doc[i].rect
        self._structural(lambda: self.doc.new_page(pno=i + 1, width=r.width, height=r.height), i + 1)

    def _delete_page(self) -> None:
        i = self.current_page()
        if self.doc.page_count <= 1:
            QMessageBox.information(self, "Excluir página", "O documento precisa ter ao menos uma página.")
            return
        if QMessageBox.question(self, "Excluir página", f"Excluir a página {i + 1}?") != QMessageBox.Yes:
            return
        self._structural(lambda: self.doc.delete_page(i), i)

    def _build_propbar(self, root: QVBoxLayout) -> None:
        """Barra contextual: mostra só as opções da ferramenta ativa."""
        bar, h = self._bar("propbar")
        bar.setFixedHeight(46)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(10)
        root.addWidget(bar)
        self.tool_title = QLabel()
        self.tool_title.setObjectName("tooltitle")
        self.tool_desc = QLabel()
        self.tool_desc.setObjectName("dim")
        h.addWidget(self.tool_title)
        h.addWidget(self.tool_desc, 1)
        self._props: dict[str, QWidget] = {}

        def group(key: str, *widgets: QWidget) -> None:
            w = QWidget()
            gh = QHBoxLayout(w)
            gh.setContentsMargins(0, 0, 0, 0)
            gh.setSpacing(6)
            for x in widgets:
                gh.addWidget(x)
            w.hide()
            h.addWidget(w)
            self._props[key] = w

        def label(text: str) -> QLabel:
            lb = QLabel(text)
            lb.setObjectName("dim")
            return lb

        def color_button(act: QAction) -> QToolButton:
            b = QToolButton()
            b.setDefaultAction(act)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            return b

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setValue(12)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setFixedWidth(84)
        group("size", label("Tamanho"), self.size_spin)

        self.color_act = QAction(color_dot(self.text_color), "Cor do texto", self)
        self.color_act.setToolTip("Escolher a cor do texto")
        self.color_act.triggered.connect(self.pick_color)
        group("tcolor", color_button(self.color_act))

        self.ann_color_act = QAction(color_dot(self.ann_color), "Cor", self)
        self.ann_color_act.setToolTip("Cor da anotação")
        self.ann_color_act.triggered.connect(self.pick_ann_color)
        group("acolor", color_button(self.ann_color_act))

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 20)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setValue(2.0)
        self.width_spin.setSuffix(" pt")
        self.width_spin.setFixedWidth(84)
        group("width", label("Espessura"), self.width_spin)

        self.fill_chk = QCheckBox("Preencher")
        group("fill", self.fill_chk)

        new_sig = QPushButton("Nova assinatura…")
        new_sig.clicked.connect(self.new_signature)
        group("sign", new_sig)

        pick_img = QPushButton("Trocar imagem…")
        pick_img.clicked.connect(self.pick_image)
        group("imgpick", pick_img)

        stamp_btn = QToolButton()
        stamp_btn.setText("Trocar carimbo")
        stamp_btn.setIcon(icon("stamp"))
        stamp_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        stamp_btn.setMenu(self.stamp_menu)
        stamp_btn.setPopupMode(QToolButton.InstantPopup)
        group("stamp", stamp_btn)

    def _build_statusbar(self, root: QVBoxLayout) -> None:
        bar, h = self._bar("statusbar")
        bar.setFixedHeight(34)
        h.setContentsMargins(14, 2, 8, 2)
        self.hint = QLabel("")
        self.hint.setObjectName("dim")
        h.addWidget(self.hint, 1)
        z = self._toolbar()
        z.setIconSize(QSize(18, 18))
        h.addWidget(z)
        self._act(z, "", lambda: self.set_zoom(self.zoom / 1.2), "Ctrl+-", "Diminuir zoom", False, "zoom_out")
        self.zoom_lbl = QLabel("125%")
        self.zoom_lbl.setMinimumWidth(52)
        self.zoom_lbl.setAlignment(Qt.AlignCenter)
        z.addWidget(self.zoom_lbl)
        self._act(z, "", lambda: self.set_zoom(self.zoom * 1.2), "Ctrl+=", "Aumentar zoom", False, "zoom_in")
        z.addSeparator()
        self._act(z, "", self.fit_width, "Ctrl+0", "Ajustar à largura", False, "fit")
        root.addWidget(bar)

    def notify(self, text: str) -> None:
        """Aviso rápido (toast) que não bloqueia o trabalho."""
        self.toast.show_message(text)

    # ---- painel lateral (miniaturas + marcadores) ---------------------------
    THUMB_W = 110

    def _build_panel(self) -> None:
        self.panel = QTabWidget()
        self.panel.setObjectName("sidetabs")
        self.panel.setMinimumWidth(215)
        self.panel.setMaximumWidth(360)
        self.thumbs = QListWidget()
        self.thumbs.setObjectName("thumbs")
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setFlow(QListWidget.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setIconSize(QSize(self.THUMB_W, int(self.THUMB_W * 1.42)))
        self.thumbs.setSpacing(6)
        self.thumbs.setMovement(QListWidget.Static)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbs.currentRowChanged.connect(self._thumb_clicked)
        self.toc = QTreeWidget()
        self.toc.setObjectName("toc")
        self.toc.setHeaderHidden(True)
        self.toc.itemClicked.connect(self._toc_clicked)
        self.panel.addTab(self.thumbs, "Miniaturas")
        self.panel.addTab(self.toc, "Marcadores")

    def fill_panel(self) -> None:
        """Cria as miniaturas (renderizadas aos poucos, sem travar a interface)."""
        self._thumb_gen += 1
        gen = self._thumb_gen
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i, (w, h) in enumerate(self.sizes):
            pm = QPixmap(self.THUMB_W, max(1, int(self.THUMB_W * h / w)))
            pm.fill(Qt.white)
            item = QListWidgetItem(str(i + 1))
            item.setIcon(flat_icon(pm))
            item.setTextAlignment(Qt.AlignHCenter)
            self.thumbs.addItem(item)
        self.thumbs.blockSignals(False)
        QTimer.singleShot(0, self, lambda: self._render_thumbs(gen, 0))

        self.toc.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, title, page in self.doc.get_toc():
            node = QTreeWidgetItem([title])
            node.setData(0, Qt.UserRole, page - 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            (stack[-1][1].addChild(node) if stack else self.toc.addTopLevelItem(node))
            stack.append((level, node))
        self.toc.expandToDepth(0)
        self.panel.setTabEnabled(1, self.toc.topLevelItemCount() > 0)

    def _render_thumbs(self, gen: int, start: int, batch: int = 6) -> None:
        if gen != self._thumb_gen:
            return
        for i in range(start, min(start + batch, self.doc.page_count)):
            self._render_thumb(i)
        if start + batch < self.doc.page_count:
            QTimer.singleShot(0, self, lambda: self._render_thumbs(gen, start + batch))

    def _render_thumb(self, i: int) -> None:
        page = self.doc[i]
        s = self.THUMB_W / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        self.thumbs.item(i).setIcon(flat_icon(pix_to_qpixmap(pix)))

    def _thumb_clicked(self, row: int) -> None:
        if row >= 0 and not self._sync:
            self.go_to_page(row)

    def _toc_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        page = item.data(0, Qt.UserRole)
        if isinstance(page, int) and page >= 0:
            self.go_to_page(page)

    def toggle_panel(self) -> None:
        self.panel.setVisible(self.panel_act.isChecked())

    # ---- páginas -------------------------------------------------------------
    def build_pages(self) -> None:
        for lb in self.labels:
            self.vbox.removeWidget(lb)
            lb.deleteLater()
        self.labels, self.sizes = [], []
        for i in range(self.doc.page_count):
            r = self.doc[i].rect
            self.sizes.append((r.width, r.height))
            lb = PageLabel(i)
            lb.mode = self.tool
            lb.get_words = self._page_words
            lb.setCursor(Qt.IBeamCursor if self.tool == "select" else Qt.CrossCursor)
            lb.clicked.connect(self.on_click)
            lb.hovered.connect(self.on_hover)
            lb.area.connect(self.on_area)
            lb.line.connect(self.on_line)
            lb.ink.connect(self.on_ink)
            lb.sel_press.connect(self._on_sel_press)
            lb.setContextMenuPolicy(Qt.CustomContextMenu)
            lb.customContextMenuRequested.connect(lambda pos, l=lb: self._context_menu(l, pos))
            self.vbox.addWidget(lb, 0, Qt.AlignHCenter)
            self.labels.append(lb)
        self.vbox.addStretch(1)
        self.apply_zoom()

    def apply_zoom(self) -> None:
        for lb, (w, h) in zip(self.labels, self.sizes):
            lb.zoom = self.zoom
            lb.setFixedSize(max(1, int(w * self.zoom)), max(1, int(h * self.zoom)))
            lb.clear()
            lb.rendered = False
        self.zoom_lbl.setText(f"{round(self.zoom * 100)}%")
        QTimer.singleShot(0, self, self.render_visible)

    def set_zoom(self, z: float) -> None:
        z = max(0.2, min(5.0, z))
        page = self.current_page()
        self.zoom = z
        self.apply_zoom()
        QTimer.singleShot(0, self, lambda: self.go_to_page(page))

    def fit_width(self) -> None:
        if not self.sizes:
            return
        avail = self.scroll.viewport().width() - 70
        self.set_zoom(avail / max(w for w, _ in self.sizes))

    def render_page(self, i: int) -> None:
        lb = self.labels[i]
        dpr = self.devicePixelRatioF()
        s = lb.zoom * dpr
        pix = self.doc[i].get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        pm = pix_to_qpixmap(pix)
        pm.setDevicePixelRatio(dpr)
        lb.setPixmap(pm)
        lb.rendered = True

    def render_visible(self) -> None:
        if not self.labels:
            return
        top = self.scroll.verticalScrollBar().value()
        h = self.scroll.viewport().height()
        for lb in self.labels:
            y0, y1 = lb.y(), lb.y() + lb.height()
            near = y1 > top - h and y0 < top + 2 * h
            far = y1 < top - 4 * h or y0 > top + 5 * h
            if near and not lb.rendered:
                self.render_page(lb.index)
            elif far and lb.rendered:
                lb.clear()
                lb.rendered = False

    def current_page(self) -> int:
        if not self.labels:
            return 0
        mid = self.scroll.verticalScrollBar().value() + self.scroll.viewport().height() // 3
        for lb in self.labels:
            if lb.y() + lb.height() + 7 >= mid:
                return lb.index
        return len(self.labels) - 1

    def go_to_page(self, i: int) -> None:
        i = max(0, min(i, len(self.labels) - 1))
        self.scroll.verticalScrollBar().setValue(max(0, self.labels[i].y() - 10))

    def _on_scroll(self) -> None:
        self.render_visible()
        self._sync = True
        cur = self.current_page()
        self.page_spin.setValue(cur + 1)
        if self.thumbs.currentRow() != cur and cur < self.thumbs.count():
            self.thumbs.setCurrentRow(cur)
            self.thumbs.scrollToItem(self.thumbs.item(cur))
        self._sync = False

    def _spin_changed(self, v: int) -> None:
        if not self._sync:
            self.go_to_page(v - 1)

    def eventFilter(self, obj, ev):  # noqa: N802
        try:
            if obj is self.scroll.viewport() and ev.type() == QEvent.Wheel \
                    and ev.modifiers() & Qt.ControlModifier:
                self.set_zoom(self.zoom * (1.12 if ev.angleDelta().y() > 0 else 1 / 1.12))
                return True
        except RuntimeError:  # objetos já destruídos durante o encerramento
            return False
        return super().eventFilter(obj, ev)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(0, self, self.fit_width)
        self._fit_ribbon()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self.toast.reposition()
        self._fit_ribbon()
        QTimer.singleShot(0, self, self.render_visible)

    # ---- ferramentas ---------------------------------------------------------
    def set_tool(self, name: str) -> None:
        if name == "sign" and PdfView.signature_png is None and not self.new_signature():
            name = "select"
        if name == "image" and self.image_png is None and not self.pick_image():
            name = "select"
        self.close_word_editor()
        self.tool = name
        self.tool_actions[name].setChecked(True)
        for lb in self.labels:
            lb.para_hover = None
            lb.mode = name
            lb.sel = None
            lb.preview_color = self.ann_color if name in ANNOT_TOOLS else QColor(ACCENT)
            lb.update()
            lb.setCursor(Qt.IBeamCursor if name == "select" else Qt.CrossCursor)
        title, desc = TOOL_INFO[name]
        if name == "stamp":
            title = f"Carimbo · {self.stamp_spec[0]}"
        self.tool_title.setText(title)
        self.tool_desc.setText(desc)
        visible = TOOL_PROPS.get(name, ())
        for key, w in self._props.items():
            w.setVisible(key in visible)
        self.hint.setText("")

    def pick_image(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", last_dir(),
                                              "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return False
        remember_dir(path)
        try:
            pm = fitz.Pixmap(path)
            self.image_png = pm.tobytes("png")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Imagem", f"Não foi possível abrir a imagem: {exc}")
            return False
        return True

    def pick_color(self) -> None:
        c = QColorDialog.getColor(self.text_color, self, "Cor do texto")
        if c.isValid():
            self.text_color = c
            self.color_act.setIcon(color_dot(c))

    def new_signature(self) -> bool:
        dlg = SignatureDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.png:
            PdfView.signature_png = dlg.png
            return True
        return False

    # ---- seleção e cópia de texto (entre páginas) ------------------------
    def _page_words(self, i: int) -> list:
        if i not in self._words_cache:
            page = self.doc[i]
            m = page.rotation_matrix
            out = []
            for w in page.get_text("words", sort=True):
                r = fitz.Rect(w[:4]).transform(m)
                out.append((QRectF(r.x0, r.y0, r.width, r.height), w[4], (w[5], w[6])))
            self._words_cache[i] = out
        return self._words_cache[i]

    def _word_under_cursor(self) -> tuple[int, int] | None:
        """(página, índice da palavra) mais próxima do cursor do mouse."""
        pos = self.container.mapFromGlobal(QCursor.pos())
        target, best = None, 1e18
        for lb in self.labels:
            top, bottom = lb.y(), lb.y() + lb.height()
            d = 0 if top <= pos.y() <= bottom else min(abs(pos.y() - top), abs(pos.y() - bottom))
            if d < best:
                target, best = lb, d
            if d == 0:
                break
        if target is None:
            return None
        words = self._page_words(target.index)
        if not words:
            return None
        x, y = (pos.x() - target.x()) / target.zoom, (pos.y() - target.y()) / target.zoom
        bi, bd = 0, 1e18
        for i, (r, _t, _ln) in enumerate(words):
            dx = max(r.left() - x, 0, x - r.right())
            dy = max(r.top() - y, 0, y - r.bottom())
            d = dx * dx + 4 * dy * dy
            if d < bd:
                bi, bd = i, d
        return target.index, bi

    def _clear_selection(self) -> None:
        self.sel_text = ""
        self._sel_anchor = self._sel_cur = None
        for lb in self.labels:
            if lb.sel is not None:
                lb.sel = None
                lb.update()

    def _on_sel_press(self, index: int) -> None:
        self._clear_selection()
        self._sel_anchor = self._word_under_cursor()
        self._sel_active = False
        self._sel_origin = QCursor.pos()
        if self._sel_anchor:
            self._sel_timer.start()

    def _sel_tick(self) -> None:
        if not (QApplication.mouseButtons() & Qt.LeftButton):
            self._sel_timer.stop()
            self._sel_finish()
            return
        vp = self.scroll.viewport()
        y = vp.mapFromGlobal(QCursor.pos()).y()  # rolagem automática ao arrastar para fora
        bar = self.scroll.verticalScrollBar()
        if y < 0:
            bar.setValue(bar.value() + max(y, -80) // 2)
        elif y > vp.height():
            bar.setValue(bar.value() + min(y - vp.height(), 80) // 2 + 1)
        if not self._sel_active and (QCursor.pos() - self._sel_origin).manhattanLength() <= 3:
            return
        cur = self._word_under_cursor()
        if cur is None:
            return
        self._sel_active = True
        self._sel_cur = cur
        self._apply_selection()

    def _apply_selection(self) -> None:
        if not (self._sel_anchor and self._sel_cur):
            return
        lo, hi = sorted((self._sel_anchor, self._sel_cur))
        for lb in self.labels:
            if lo[0] <= lb.index <= hi[0]:
                first = lo[1] if lb.index == lo[0] else 0
                last = hi[1] if lb.index == hi[0] else 10 ** 9
                lb.sel = (first, last)
            else:
                lb.sel = None
            lb.update()

    def _collect_text(self) -> str:
        if not (self._sel_anchor and self._sel_cur):
            return ""
        lo, hi = sorted((self._sel_anchor, self._sel_cur))
        parts = []
        for pg in range(lo[0], hi[0] + 1):
            words = self._page_words(pg)
            a = lo[1] if pg == lo[0] else 0
            b = hi[1] if pg == hi[0] else len(words) - 1
            out, prev = [], None
            for _r, text, ln in words[a:b + 1]:
                if prev is not None:
                    out.append(" " if ln == prev else "\n")
                out.append(text)
                prev = ln
            if out:
                parts.append("".join(out))
        return "\n\n".join(parts)

    def _sel_finish(self) -> None:
        if not self._sel_active:
            self._clear_selection()
            return
        self.sel_text = self._collect_text()
        pages = abs(self._sel_cur[0] - self._sel_anchor[0]) + 1
        self.hint.setText(f"{len(self.sel_text.split())} palavra(s) em {pages} página(s) — Ctrl+C para copiar")

    def select_all_text(self) -> None:
        if self.tool != "select":
            self.set_tool("select")
        first = next(((i, 0) for i in range(self.doc.page_count) if self._page_words(i)), None)
        last = next(((i, len(self._page_words(i)) - 1) for i in reversed(range(self.doc.page_count))
                     if self._page_words(i)), None)
        if not first:
            self.hint.setText("Este documento não tem texto selecionável (use o OCR).")
            return
        self._sel_anchor, self._sel_cur, self._sel_active = first, last, True
        self._apply_selection()
        self._sel_finish()

    def copy_selection(self) -> None:
        if self.sel_text:
            QApplication.clipboard().setText(self.sel_text)
            self.notify("Texto copiado")

    def _context_menu(self, lb: PageLabel, pos) -> None:
        menu = QMenu(self)
        copy = menu.addAction("Copiar texto")
        copy.setEnabled(bool(self.sel_text))
        copy.triggered.connect(self.copy_selection)
        menu.addAction("Selecionar tudo", self.select_all_text)
        page = self.doc[lb.index]
        annot = annots.annot_at(page, fitz.Point(pos.x() / lb.zoom, pos.y() / lb.zoom))
        if annot is not None:
            menu.addSeparator()
            kind = annots.describe(annot).lower()
            if annots.editable_text(annot):
                menu.addAction(f"Editar texto da {kind}…", lambda: self._edit_annot_text(lb.index, annot, page))
            menu.addAction(f"Excluir {kind}", lambda: self._delete_annot(lb.index, annot, page))
        menu.addSeparator()
        menu.addAction("Ajustar à largura", self.fit_width)
        menu.exec(lb.mapToGlobal(pos))

    def _delete_annot(self, i: int, annot, page) -> None:
        """`page` precisa ser o mesmo objeto de página que originou a anotação."""
        if not self._confirm_signed():
            return
        self._push_undo()
        page.delete_annot(annot)
        self._after_edit(i)

    def _edit_annot_text(self, i: int, annot, page) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Editar anotação", "Texto:",
                                                 annot.info.get("content", ""))
        if ok and self._confirm_signed():
            self._push_undo()
            annots.set_text(annot, text)
            self._after_edit(i)

    # ---- edição --------------------------------------------------------------
    HISTORY_MAX = 40                  # nº máximo de passos
    HISTORY_BYTES = 300 * 1024 * 1024  # e teto de memória do histórico

    def _push_undo(self) -> None:
        self.undo_stack.append(self._snapshot())
        self.redo_stack.clear()           # uma edição nova invalida o "refazer"
        del self.undo_stack[:-self.HISTORY_MAX]
        while len(self.undo_stack) > 1 and sum(len(x) for x in self.undo_stack) > self.HISTORY_BYTES:
            self.undo_stack.pop(0)
        self.undo_act.setEnabled(True)
        self.redo_act.setEnabled(False)

    def _after_edit(self, page_index: int) -> None:
        self.__dict__.pop("_para_cache", None)
        self._words_cache.pop(page_index, None)
        self.set_modified(True)
        self.render_page(page_index)
        self.labels[page_index].update()
        self._render_thumb(page_index)

    def set_modified(self, value: bool) -> None:
        if value != self.modified:
            self.modified = value
            self.modified_changed.emit(value)
        if not value:
            recovery.discard(self.rid)

    def autosave(self) -> None:
        """Cópia de segurança do que ainda não foi salvo (a cada 45 s, só se houver alterações)."""
        if not self.modified:
            return
        try:
            enc = fitz.PDF_ENCRYPT_AES_256 if self.password else fitz.PDF_ENCRYPT_NONE
            kw = {"user_pw": self.password, "owner_pw": self.password} if self.password else {}
            data = self.doc.tobytes(garbage=0, deflate=True, encryption=enc, **kw)
            recovery.write(self.rid, data, title=Path(self.path).name if self.path else "Documento",
                           original=self.path, encrypted=bool(self.password))
        except Exception:  # noqa: BLE001 — a recuperação nunca pode atrapalhar o trabalho
            pass

    def _restore(self, data: bytes) -> None:
        self.close_word_editor()
        self.__dict__.pop("_para_cache", None)
        self.doc.close()
        self.doc = fitz.open(stream=data, filetype="pdf")
        if self.labels and len(self.labels) != self.doc.page_count:  # desfazer/refazer mudou o nº de páginas
            self.build_pages()
            self.page_spin.setRange(1, max(1, self.doc.page_count))
            self.page_total.setText(f"  de {self.doc.page_count}  ")
        for lb in self.labels:
            lb.rendered = False
            lb.clear()
        self.clear_search()
        self._words_cache.clear()
        self.render_visible()
        self.fill_panel()
        self.undo_act.setEnabled(bool(self.undo_stack))
        self.redo_act.setEnabled(bool(self.redo_stack))
        self.set_modified(True)

    def _snapshot(self) -> bytes:
        return self.doc.tobytes(garbage=0, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)

    def _abort_edit(self) -> None:
        """Reverte uma edição que falhou, sem entrar no histórico de refazer."""
        if self.undo_stack:
            self._restore(self.undo_stack.pop())

    def do_undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())

    def do_redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())

    def _confirm_signed(self) -> bool:
        if self.is_signed and not self._signed_ok:
            r = QMessageBox.question(self, "Documento assinado",
                                     "Este documento tem assinatura digital. Editar e salvar vai "
                                     "invalidar a(s) assinatura(s). Continuar?")
            if r != QMessageBox.Yes:
                return False
            self._signed_ok = True
        return True

    def _ann_rgb(self) -> tuple[float, float, float]:
        c = self.ann_color
        return (c.redF(), c.greenF(), c.blueF())

    def pick_ann_color(self) -> None:
        c = QColorDialog.getColor(self.ann_color, self, "Cor das anotações")
        if c.isValid():
            self.ann_color = c
            self.ann_color_act.setIcon(color_dot(c))
            for lb in self.labels:
                if lb.mode in ANNOT_TOOLS:
                    lb.preview_color = c

    def use_stamp(self, text: str, color: str) -> None:
        self.stamp_spec = (text, color)
        self.set_tool("stamp")

    def custom_stamp(self) -> None:
        text, ok = QInputDialog.getText(self, "Carimbo personalizado", "Texto do carimbo:")
        if ok and text.strip():
            self.use_stamp(text.strip().upper(), self.ann_color.name())

    def _edit(self, i: int, action, hint: str = "") -> bool:
        """Snapshot para desfazer + executa a ação; em caso de erro, reverte."""
        self._push_undo()
        try:
            note = action()
        except Exception as exc:  # noqa: BLE001
            self._abort_edit()
            QMessageBox.warning(self, "Não foi possível aplicar", str(exc))
            return False
        self._after_edit(i)
        if isinstance(note, str) and note.strip():
            self.hint.setText(note.strip())
        elif hint:
            self.hint.setText(hint)
        return True

    def on_click(self, i: int, pt: QPointF) -> None:
        if not self._confirm_signed():
            return
        page = self.doc[i]
        p = fitz.Point(pt.x(), pt.y())
        if self.tool == "addtext":
            text, ok = QInputDialog.getMultiLineText(self, "Adicionar texto", "Texto:")
            if ok and text.strip():
                c = self.text_color
                self._edit(i, lambda: ops.add_text(page, p, text, self.size_spin.value(),
                                                   (c.redF(), c.greenF(), c.blueF())))
        elif self.tool == "note":
            text, ok = QInputDialog.getMultiLineText(self, "Nova nota", "Comentário:")
            if ok and text.strip():
                self._edit(i, lambda: annots.add_note(page, p, text))
        elif self.tool == "edittext":
            self.close_word_editor()
            w = textedit.word_at(page, p)
            if w:
                self.open_word_editor(i, w)
            else:
                self.edit_paragraph(i, p)

    def edit_paragraph(self, i: int, p) -> None:
        page = self.doc[i]
        self.setCursor(Qt.WaitCursor)  # a 1ª vez indexa as fontes do sistema
        try:
            block = textedit.block_at(page, p)
            if block:
                textedit.font_index()
        finally:
            self.unsetCursor()
        if not block:
            self.hint.setText("Nenhum texto editável nesse ponto (página digitalizada? use o OCR).")
            return
        dlg = ParagraphEditDialog(block, self)
        if dlg.exec() != QDialog.Accepted:
            return
        values = dlg.values()
        if values["new_text"] == block["text"] and values["family"] == "original" \
                and abs(values["size"] - block["size"]) < 0.05 and tuple(values["color"]) == tuple(block["color"]) \
                and values["align"] == block["align"] \
                and values["bold"] == bool(block["flags"] & 16) and values["italic"] == bool(block["flags"] & 2):
            return  # nada mudou
        self._edit(i, lambda: textedit.replace_block(page, block, **values))

    # ---- edição por palavra ----------------------------------------------------
    def _para_rects(self, i: int) -> list:
        cache = self.__dict__.setdefault("_para_cache", {})
        if i not in cache:
            cache[i] = [fitz.Rect(b[:4]) for b in self.doc[i].get_text("blocks") if b[6] == 0 and b[4].strip()]
        return cache[i]

    def on_hover(self, i: int, pt) -> None:
        lb = self.labels[i]
        new = None
        if pt is not None:
            q = fitz.Point(pt.x(), pt.y())
            for r in self._para_rects(i):
                if r.contains(q):
                    new = QRectF(r.x0, r.y0, r.width, r.height)
                    break
        if new != lb.para_hover:
            for other in self.labels:
                if other is not lb and other.para_hover is not None:
                    other.para_hover = None
                    other.update()
            lb.para_hover = new
            lb.update()

    def close_word_editor(self) -> None:
        bar = getattr(self, "_wordbar", None)
        if bar is not None:
            self._wordbar = None
            bar.deleteLater()
        for lb in self.labels:
            if lb.para_sel is not None or lb.word_sel is not None:
                lb.para_sel = lb.word_sel = None
                lb.update()

    def open_word_editor(self, i: int, w: dict) -> None:
        lb = self.labels[i]
        z = lb.zoom
        lb.para_sel = QRectF(w["para"][0], w["para"][1], w["para"][2] - w["para"][0], w["para"][3] - w["para"][1])
        lb.word_sel = QRectF(w["x0"], w["y0"], w["x1"] - w["x0"], w["y1"] - w["y0"])
        lb.update()
        host = lb.parentWidget() or lb
        bar = QFrame(host)
        bar.setObjectName("wordbar")
        bar.state = {"color": QColor.fromRgbF(*w["color"][:3])}
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 5, 6, 5)
        h.setSpacing(3)
        edit = QLineEdit(w["text"])
        edit.setMinimumWidth(max(80, min(150, int((w["x1"] - w["x0"]) * z) + 24)))
        size = QDoubleSpinBox()
        size.setRange(4, 200)
        size.setDecimals(1)
        size.setValue(round(w["size"], 1))
        size.setToolTip("Tamanho")
        fam = QComboBox()
        fam.setMaximumWidth(100)
        fam.setToolTip("Fonte")
        fam.addItem("Original", "original")
        for lab, key in (("Helvetica", "sans"), ("Times", "serif"), ("Courier", "mono")):
            fam.addItem(lab, key)
        self.setCursor(Qt.WaitCursor)
        try:
            for k in textedit.system_families():
                fam.addItem(k.title(), k)
        finally:
            self.unsetCursor()
        bold = QToolButton(); bold.setText("B"); bold.setCheckable(True); bold.setChecked(bool(w["flags"] & 16))
        bold.setToolTip("Negrito")
        ital = QToolButton(); ital.setText("I"); ital.setCheckable(True); ital.setChecked(bool(w["flags"] & 2))
        ital.setToolTip("Itálico")
        bold.setObjectName("wb_b"); ital.setObjectName("wb_i")
        col = QToolButton(); col.setIcon(color_dot(bar.state["color"])); col.setToolTip("Cor")
        ok = QPushButton("Aplicar"); ok.setObjectName("wb_ok")
        para = QPushButton("¶"); para.setToolTip("Editar o parágrafo inteiro"); para.setObjectName("wb_para")
        close = QToolButton(); close.setText("✕"); close.setToolTip("Cancelar (Esc)")
        for x in (edit, fam, size, bold, ital, col, ok, para, close):
            h.addWidget(x)

        def pick():
            c = QColorDialog.getColor(bar.state["color"], self, "Cor da palavra")
            if c.isValid():
                bar.state["color"] = c
                col.setIcon(color_dot(c))

        def apply():
            new = edit.text().strip()
            c = bar.state["color"]
            changed = (new != w["text"] or fam.currentData() != "original" or abs(size.value() - w["size"]) > 0.05
                       or bold.isChecked() != bool(w["flags"] & 16) or ital.isChecked() != bool(w["flags"] & 2)
                       or (c.redF(), c.greenF(), c.blueF()) != tuple(w["color"][:3]))
            self.close_word_editor()
            if not changed:
                return
            page = self.doc[i]
            rgb = (c.redF(), c.greenF(), c.blueF())
            sz = size.value() if abs(size.value() - w["size"]) > 0.05 else None   # None = mantém o original exato
            bd = bold.isChecked() if bold.isChecked() != bool(w["flags"] & 16) else None
            it = ital.isChecked() if ital.isChecked() != bool(w["flags"] & 2) else None
            self._edit(i, lambda: textedit.replace_word(
                           page, w, new, family=fam.currentData(), size=sz, bold=bd, italic=it, color=rgb),
                       f"Palavra trocada por “{new}”.")

        def whole():
            self.close_word_editor()
            self.edit_paragraph(i, fitz.Point((w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2))

        col.clicked.connect(pick)
        ok.clicked.connect(apply)
        edit.returnPressed.connect(apply)
        para.clicked.connect(whole)
        close.clicked.connect(self.close_word_editor)
        QShortcut(QKeySequence(Qt.Key_Escape), bar, activated=self.close_word_editor)
        bar.adjustSize()
        top = lb.mapTo(host, QPoint(int(w["x0"] * z) - 8, int(w["para"][1] * z) - bar.height() - 10))
        left = lb.mapTo(host, QPoint(0, 0)).x()
        bx = max(left, min(top.x(), left + lb.width() - bar.width()))
        by = top.y()
        if by < 4:
            by = lb.mapTo(host, QPoint(0, int(w["para"][3] * z) + 10)).y()
        bar.move(bx, by)
        bar.raise_()
        bar.show()
        edit.setFocus()
        edit.selectAll()
        self._wordbar = bar

    def on_area(self, i: int, rect: QRectF) -> None:
        if not self._confirm_signed():
            return
        page = self.doc[i]
        r = fitz.Rect(rect.left(), rect.top(), rect.right(), rect.bottom())
        t, color, width = self.tool, self._ann_rgb(), self.width_spin.value()
        if t == "highlight":
            self._edit(i, lambda: ops.highlight(page, r))
        elif t == "erase":
            self._edit(i, lambda: ops.erase(page, r))
        elif t == "image" and self.image_png:
            self._edit(i, lambda: ops.add_image(page, r, self.image_png))
        elif t == "sign" and PdfView.signature_png:
            self._edit(i, lambda: ops.add_image(page, r, PdfView.signature_png))
        elif t in ("rect", "ellipse"):
            self._edit(i, lambda: annots.add_shape(page, r, t, color, width, self.fill_chk.isChecked()))
        elif t == "freetext":
            text, ok = QInputDialog.getMultiLineText(self, "Caixa de texto", "Texto:")
            if ok and text.strip():
                self._edit(i, lambda: annots.add_freetext(page, r, text, self.size_spin.value(), color))
        elif t == "stamp":
            text, col = self.stamp_spec
            self._edit(i, lambda: ops.add_image(page, r, make_stamp_png(text, col)))

    def on_line(self, i: int, a: QPointF, b: QPointF) -> None:
        if not self._confirm_signed():
            return
        page = self.doc[i]
        pa, pb = fitz.Point(a.x(), a.y()), fitz.Point(b.x(), b.y())
        self._edit(i, lambda: annots.add_line(page, pa, pb, self._ann_rgb(), self.width_spin.value(),
                                              arrow=self.tool == "arrow"))

    def on_ink(self, i: int, pts: list) -> None:
        if not self._confirm_signed():
            return
        page = self.doc[i]
        stroke = [(p.x(), p.y()) for p in pts]
        self._edit(i, lambda: annots.add_ink(page, [stroke], self._ann_rgb(), self.width_spin.value()))

    # ---- assinatura digital ---------------------------------------------------
    def sign_digital(self) -> None:
        if self.password:
            QMessageBox.information(self, "Assinar digitalmente",
                                    "Este PDF é protegido por senha. Remova a senha antes de assinar "
                                    "(Início › Criptografar PDF › Remover senha).")
            return
        dlg = CertSignDialog(self.doc.page_count, self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        default = str(Path(self.path).with_name(Path(self.path).stem + "_assinado.pdf")) if self.path \
            else str(Path(last_dir()) / "documento_assinado.pdf")
        out, _ = QFileDialog.getSaveFileName(self, "Salvar documento assinado", default, "PDF (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        remember_dir(out)
        try:
            if self.path and not self.modified:
                data = Path(self.path).read_bytes()  # preserva assinaturas anteriores
            else:
                if self.is_signed and QMessageBox.question(
                        self, "Assinar", "As edições não salvas vão invalidar as assinaturas já existentes. "
                                         "Continuar?") != QMessageBox.Yes:
                    return
                data = self.doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            box = None
            if v["visible"]:
                page = self.doc[v["page"]]
                r, w, h, m = page.rect, 220, 70, 36
                x0 = {0: r.x1 - m - w, 1: r.x0 + m, 2: (r.x0 + r.x1 - w) / 2, 3: r.x1 - m - w}[v["position"]]
                y0 = r.y0 + m if v["position"] == 3 else r.y1 - m - h
                un = ops._rect(page, fitz.Rect(x0, y0, x0 + w, y0 + h))
                pdf = fitz.Rect(un).transform(~page.transformation_matrix)
                box = (pdf.x0, pdf.y0, pdf.x1, pdf.y1)
            self.setCursor(Qt.WaitCursor)
            signing.sign_pdf(data, out, v["pfx"], v["password"], reason=v["reason"],
                             location=v["location"], visible=v["visible"],
                             page_index=v["page"], box=box)
        except Exception as exc:  # noqa: BLE001
            self.unsetCursor()
            QMessageBox.critical(self, "Erro ao assinar", str(exc))
            return
        self.unsetCursor()
        QMessageBox.information(self, "Assinado", f"Documento assinado digitalmente:\n{out}")
        self.open_requested.emit(out)

    def verify_signatures(self) -> None:
        if not self.path or self.modified:
            QMessageBox.information(self, "Verificar assinaturas",
                                    "Salve o documento antes de verificar (a verificação usa o arquivo em disco).")
            return
        self.setCursor(Qt.WaitCursor)
        try:
            results = signing.verify(Path(self.path).read_bytes())
        except Exception as exc:  # noqa: BLE001
            self.unsetCursor()
            QMessageBox.critical(self, "Erro", str(exc))
            return
        self.unsetCursor()
        show_verification(self, results)

    def fill_forms(self) -> None:
        if not self._confirm_signed():
            return
        if not self.doc.is_form_pdf:
            QMessageBox.information(self, "Formulário", "Este PDF não possui campos de formulário.")
            return
        dlg = FormDialog(self.doc, self)
        if dlg.exec() == QDialog.Accepted:
            self._push_undo()
            dlg.apply()
            for lb in self.labels:
                lb.rendered = False
            self._words_cache.clear()
            self.render_visible()
            self.fill_panel()
            self.set_modified(True)

    # ---- busca ---------------------------------------------------------------
    def clear_search(self) -> None:
        self.hits, self.hit_i, self._query = [], -1, ""
        for lb in self.labels:
            lb.hits, lb.cur_hit = [], None
            lb.update()
        self.search_lbl.setText("")

    def find_next(self) -> None:
        q = self.search.text().strip()
        if not q:
            self.clear_search()
            return
        if q != self._query:
            self.clear_search()
            self._query = q
            for i in range(self.doc.page_count):
                page = self.doc[i]
                for r in page.search_for(q):
                    rr = fitz.Rect(r).transform(page.rotation_matrix)
                    self.hits.append((i, QRectF(rr.x0, rr.y0, rr.width, rr.height)))
            for lb in self.labels:
                lb.hits = [h[1] for h in self.hits if h[0] == lb.index]
        if not self.hits:
            self.search_lbl.setText(" Nenhum resultado")
            return
        self.hit_i = (self.hit_i + 1) % len(self.hits)
        page_i, rect = self.hits[self.hit_i]
        for lb in self.labels:
            lb.cur_hit = rect if lb.index == page_i else None
            lb.update()
        lb = self.labels[page_i]
        self.scroll.verticalScrollBar().setValue(max(0, int(lb.y() + rect.y() * self.zoom) - 120))
        self.search_lbl.setText(f" {self.hit_i + 1}/{len(self.hits)}")

    # ---- salvar / imprimir ---------------------------------------------------
    def save(self) -> bool:
        return self._write(self.path) if self.path else self.save_as()

    def save_as(self) -> bool:
        default = self.path or getattr(self, "suggest_path", None) or str(Path(last_dir()) / "documento.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar como", default, "PDF (*.pdf)")
        if not path:
            return False
        remember_dir(path)
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if self._write(path):
            self.path = path
            self.title_changed.emit(Path(path).name)
            return True
        return False

    def _write(self, path: str) -> bool:
        try:
            if self.password:
                data = self.doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
                                        user_pw=self.password, owner_pw=self.password)
            else:
                data = self.doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            ops.write_file(path, data)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar", str(exc))
            return False
        self.set_modified(False)
        self.notify(f"Salvo: {Path(path).name}")
        return True

    def print_doc(self) -> None:
        n = self.doc.page_count
        from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter  # carregado só ao imprimir
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QAbstractPrintDialog.PrintPageRange)
        dlg.setMinMax(1, n)
        if dlg.exec() != QDialog.Accepted:
            return
        first, last = 1, n
        if printer.printRange() == QPrinter.PageRange:
            first, last = printer.fromPage() or 1, printer.toPage() or n
        dpi = printer.resolution()
        render_dpi = min(dpi, 300)
        target = printer.pageLayout().paintRectPixels(dpi)
        painter = QPainter(printer)
        self.setCursor(Qt.WaitCursor)
        try:
            for i in range(first - 1, last):
                if i > first - 1:
                    printer.newPage()
                pix = self.doc[i].get_pixmap(dpi=render_dpi, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                scaled = img.scaled(target.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawImage(0, 0, scaled)
        finally:
            painter.end()
            self.unsetCursor()

    # ---- fechamento ----------------------------------------------------------
    def confirm_close(self) -> bool:
        """True se a aba pode ser fechada."""
        if not self.modified:
            return True
        name = Path(self.path).name if self.path else "este documento"
        box = QMessageBox(QMessageBox.Question, "Alterações não salvas",
                          f"Salvar as alterações em {name}?", parent=self)
        save = box.addButton("Salvar", QMessageBox.AcceptRole)
        discard = box.addButton("Descartar", QMessageBox.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is save:
            return self.save()
        if box.clickedButton() is discard:
            recovery.discard(self.rid)
            return True
        return False
