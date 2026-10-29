"""Diálogos das ferramentas do Vértice PDF."""
from __future__ import annotations

from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPainterPath,
                           QPen, QPixmap, QTransform)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QPlainTextEdit,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

import ops
from ui_common import FileList, PathPicker, PolishedDialog, TaskDialog, Worker, last_dir, remember_dir

IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def _primary(text: str, slot) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("primary")
    btn.clicked.connect(slot)
    return btn


def _run_each(files: list[str], fn, progress) -> str:
    """Executa fn(arquivo)->str para cada arquivo, sem parar no primeiro erro."""
    lines = []
    for i, f in enumerate(files):
        try:
            lines.append(f"✔ {Path(f).name}: {fn(f)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"✘ {Path(f).name}: {exc}")
        progress(i + 1, len(files))
    return "\n".join(lines)


def _ask_save_pdf(parent, title: str, default: str) -> str | None:
    if not Path(default).is_absolute():
        default = str(Path(last_dir()) / default)
    path, _ = QFileDialog.getSaveFileName(parent, title, default, "PDF (*.pdf)")
    if path and not path.lower().endswith(".pdf"):
        path += ".pdf"
    remember_dir(path)
    return path or None


# ==========================================================================
# Processamento em lote (combinar / dividir / comprimir / converter)
# ==========================================================================
class BatchDialog(TaskDialog):
    def __init__(self, parent=None, tab: int = 0):
        super().__init__("Processamento em lote", parent)
        self.resize(660, 560)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("sidetabs")
        self.body.addWidget(self.tabs)
        self._build_merge()
        self._build_split()
        self._build_compress()
        self._build_convert()
        self.tabs.setCurrentIndex(tab)

    # ---- Combinar -------------------------------------------------------
    def _build_merge(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Arraste os PDFs aqui ou use Adicionar. A ordem da lista é a ordem final:"))
        self.m_files = FileList()
        v.addWidget(self.m_files)
        v.addWidget(QLabel("Salvar como:"))
        self.m_out = PathPicker("save", "Salvar PDF combinado", placeholder="combinado.pdf")
        v.addWidget(self.m_out)
        v.addWidget(_primary("Combinar PDFs", self._run_merge))
        self.tabs.addTab(w, "Combinar")

    def _run_merge(self) -> None:
        files = self.m_files.files()
        if len(files) < 2:
            QMessageBox.warning(self, "Combinar", "Adicione pelo menos 2 PDFs.")
            return
        out = self.m_out.text() or _ask_save_pdf(self, "Salvar PDF combinado", "combinado.pdf")
        if not out:
            return
        self.m_out.setText(out)

        def done(_):
            self.result_path = out
            QMessageBox.information(self, "Combinar", f"PDF criado:\n{out}")

        self.start(lambda prog: ops.merge(files, out, prog), done)

    # ---- Dividir --------------------------------------------------------
    def _build_split(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        self.s_file = FileList(single=True)
        v.addWidget(self.s_file)
        form = QFormLayout()
        self.s_mode = QComboBox()
        self.s_mode.addItems(["Uma página por arquivo", "A cada N páginas", "Intervalos personalizados"])
        self.s_n = QSpinBox()
        self.s_n.setRange(1, 9999)
        self.s_n.setValue(2)
        self.s_ranges = QLineEdit()
        self.s_ranges.setPlaceholderText("Ex.: 1-3, 5, 7-  (cada intervalo vira um arquivo)")
        self.s_out = PathPicker("dir", "Pasta de saída", placeholder="Vazio = mesma pasta do arquivo")
        form.addRow("Modo:", self.s_mode)
        form.addRow("N:", self.s_n)
        form.addRow("Intervalos:", self.s_ranges)
        form.addRow("Pasta de saída:", self.s_out)
        v.addLayout(form)
        self.s_mode.currentIndexChanged.connect(self._split_mode_changed)
        self._split_mode_changed(0)
        v.addWidget(_primary("Dividir PDF", self._run_split))
        self.tabs.addTab(w, "Dividir")

    def _split_mode_changed(self, idx: int) -> None:
        self.s_n.setEnabled(idx == 1)
        self.s_ranges.setEnabled(idx == 2)

    def _run_split(self) -> None:
        files = self.s_file.files()
        if not files:
            QMessageBox.warning(self, "Dividir", "Escolha um PDF.")
            return
        src = files[0]
        try:
            with ops.open_pdf(src) as d:
                n = d.page_count
            mode = self.s_mode.currentIndex()
            if mode == 0:
                groups = ops.groups_every(n, 1)
            elif mode == 1:
                groups = ops.groups_every(n, self.s_n.value())
            else:
                groups = ops.parse_ranges(self.s_ranges.text(), n)
        except (ValueError, ops.PasswordRequired) as exc:
            QMessageBox.warning(self, "Dividir", str(exc))
            return
        outdir = self.s_out.text() or str(Path(src).parent)

        def done(outs):
            self.result_path = outs[0] if outs else None
            QMessageBox.information(self, "Dividir", f"{len(outs)} arquivo(s) criado(s) em:\n{outdir}")

        self.start(lambda prog: ops.split(src, groups, outdir, prog), done)

    # ---- Comprimir ------------------------------------------------------
    def _build_compress(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("PDFs para comprimir:"))
        self.c_files = FileList()
        v.addWidget(self.c_files)
        form = QFormLayout()
        self.c_level = QComboBox()
        self.c_level.addItems(["Leve (sem perda de qualidade)", "Média (recomendado)",
                               "Forte (menor tamanho)"])
        self.c_level.setCurrentIndex(1)
        self.c_out = PathPicker("dir", "Pasta de saída", placeholder="Vazio = mesma pasta de cada arquivo")
        form.addRow("Compressão:", self.c_level)
        form.addRow("Pasta de saída:", self.c_out)
        v.addLayout(form)
        v.addWidget(QLabel("Os originais não são alterados: o resultado recebe o sufixo “_comprimido”."))
        v.addWidget(_primary("Comprimir", self._run_compress))
        self.tabs.addTab(w, "Comprimir")

    def _run_compress(self) -> None:
        files = self.c_files.files()
        if not files:
            QMessageBox.warning(self, "Comprimir", "Adicione ao menos um PDF.")
            return
        level = ("leve", "media", "forte")[self.c_level.currentIndex()]
        folder = self.c_out.text()

        def one(f: str) -> str:
            out = Path(folder or Path(f).parent) / f"{Path(f).stem}_comprimido.pdf"
            before, after = ops.compress(f, str(out), level)
            saved = (1 - after / before) * 100 if before else 0
            return f"{ops.fmt_size(before)} → {ops.fmt_size(after)} (−{saved:.0f}%)"

        self.start(lambda prog: _run_each(files, one, prog),
                   lambda txt: QMessageBox.information(self, "Comprimir", txt))

    # ---- Converter ------------------------------------------------------
    def _build_convert(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("PDFs para converter:"))
        self.v_files = FileList()
        v.addWidget(self.v_files)
        form = QFormLayout()
        self.v_fmt = QComboBox()
        self.v_fmt.addItems(["Imagens PNG", "Imagens JPG", "Texto (TXT)"])
        self.v_dpi = QSpinBox()
        self.v_dpi.setRange(50, 600)
        self.v_dpi.setValue(150)
        self.v_dpi.setSuffix(" dpi")
        self.v_out = PathPicker("dir", "Pasta de saída", placeholder="Vazio = mesma pasta de cada arquivo")
        form.addRow("Converter para:", self.v_fmt)
        form.addRow("Resolução:", self.v_dpi)
        form.addRow("Pasta de saída:", self.v_out)
        v.addLayout(form)
        v.addWidget(_primary("Converter", self._run_convert))
        self.tabs.addTab(w, "Converter")

    def _run_convert(self) -> None:
        files = self.v_files.files()
        if not files:
            QMessageBox.warning(self, "Converter", "Adicione ao menos um PDF.")
            return
        kind = self.v_fmt.currentIndex()
        dpi = self.v_dpi.value()
        folder = self.v_out.text()

        def one(f: str) -> str:
            base = Path(folder or Path(f).parent)
            if kind == 2:
                n = ops.to_text(f, str(base / f"{Path(f).stem}.txt"))
                return f"{n} página(s) → {Path(f).stem}.txt"
            fmt = "png" if kind == 0 else "jpg"
            n = ops.to_images(f, str(base / f"{Path(f).stem}_paginas"), fmt, dpi)
            return f"{n} imagem(ns) em {Path(f).stem}_paginas/"

        self.start(lambda prog: _run_each(files, one, prog),
                   lambda txt: QMessageBox.information(self, "Converter", txt))


# ==========================================================================
# Criptografar / remover senha
# ==========================================================================
class EncryptDialog(TaskDialog):
    def __init__(self, parent=None):
        super().__init__("Criptografar PDF", parent)
        self.file = PathPicker("open", "Escolher PDF", placeholder="Arquivo PDF")
        self.body.addWidget(self.file)

        row = QHBoxLayout()
        self.r_protect = QRadioButton("Proteger com senha")
        self.r_remove = QRadioButton("Remover senha")
        self.r_protect.setChecked(True)
        row.addWidget(self.r_protect)
        row.addWidget(self.r_remove)
        row.addStretch(1)
        self.body.addLayout(row)

        form = QFormLayout()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.lbl_pw = QLabel("Senha:")
        form.addRow(self.lbl_pw, self.pw)
        self.body.addLayout(form)

        self.protect_box = QWidget()
        pf = QFormLayout(self.protect_box)
        pf.setContentsMargins(0, 0, 0, 0)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.owner = QLineEdit()
        self.owner.setEchoMode(QLineEdit.Password)
        self.owner.setPlaceholderText("Opcional — necessária para alterar as permissões")
        self.c_print = QCheckBox("Permitir impressão")
        self.c_copy = QCheckBox("Permitir copiar texto")
        self.c_edit = QCheckBox("Permitir edição e anotações")
        self.c_print.setChecked(True)
        self.c_copy.setChecked(True)
        pf.addRow("Confirmar senha:", self.pw2)
        pf.addRow("Senha do proprietário:", self.owner)
        pf.addRow("", self.c_print)
        pf.addRow("", self.c_copy)
        pf.addRow("", self.c_edit)
        self.body.addWidget(self.protect_box)

        self.run_btn = _primary("Proteger PDF", self._run)
        self.body.addWidget(self.run_btn)
        self.r_protect.toggled.connect(self._mode_changed)

    def _mode_changed(self, protect: bool) -> None:
        self.protect_box.setVisible(protect)
        self.lbl_pw.setText("Senha:" if protect else "Senha atual:")
        self.run_btn.setText("Proteger PDF" if protect else "Remover senha")

    def _run(self) -> None:
        src = self.file.text()
        if not src or not Path(src).is_file():
            QMessageBox.warning(self, "Criptografar", "Escolha um arquivo PDF válido.")
            return
        pw = self.pw.text()
        if not pw:
            QMessageBox.warning(self, "Criptografar", "Informe a senha.")
            return
        protect = self.r_protect.isChecked()
        if protect and pw != self.pw2.text():
            QMessageBox.warning(self, "Criptografar", "As senhas não conferem.")
            return
        suffix = "_protegido" if protect else "_sem_senha"
        out = _ask_save_pdf(self, "Salvar PDF", str(Path(src).with_name(Path(src).stem + suffix + ".pdf")))
        if not out:
            return
        if Path(out).resolve() == Path(src).resolve():
            QMessageBox.warning(self, "Criptografar", "Escolha um nome diferente do arquivo original.")
            return

        if protect:
            def job(_prog):
                ops.encrypt(src, out, pw, self.owner.text(), self.c_print.isChecked(),
                            self.c_copy.isChecked(), self.c_edit.isChecked())
        else:
            def job(_prog):
                ops.decrypt(src, out, pw)

        def done(_):
            self.result_path = out
            QMessageBox.information(self, "Concluído", f"Arquivo salvo em:\n{out}")

        self.start(job, done)

    def _fail(self, msg: str) -> None:  # senha errada vira mensagem amigável
        super()._fail("Não foi possível abrir o PDF. Verifique a senha.\n\n" + msg
                      if "senha" in msg.lower() else msg)


# ==========================================================================
# OCR
# ==========================================================================
class OcrDialog(TaskDialog):
    LANGS = [("Português + Inglês", "por+eng"), ("Português", "por"),
             ("Inglês", "eng"), ("Espanhol", "spa"), ("Espanhol + Inglês", "spa+eng")]

    def __init__(self, parent=None):
        super().__init__("OCR — reconhecer texto", parent)
        self.body.addWidget(QLabel("Gera um novo PDF pesquisável a partir de documentos digitalizados."))
        self.file = PathPicker("open", "Escolher PDF", placeholder="PDF digitalizado")
        self.body.addWidget(self.file)
        form = QFormLayout()
        self.lang = QComboBox()
        for label, code in self.LANGS:
            self.lang.addItem(label, code)
        self.dpi = QSpinBox()
        self.dpi.setRange(100, 400)
        self.dpi.setValue(200)
        self.dpi.setSuffix(" dpi")
        form.addRow("Idioma:", self.lang)
        form.addRow("Qualidade:", self.dpi)
        self.body.addLayout(form)
        self.run_btn = _primary("Executar OCR", self._run)
        if not ops.find_tesseract():
            warn = QLabel("⚠ Tesseract não encontrado. Instale-o e reabra esta janela "
                          "(instruções no README).")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#f5a623;")
            self.body.addWidget(warn)
            self.run_btn.setEnabled(False)
        self.body.addWidget(self.run_btn)

    def _run(self) -> None:
        src = self.file.text()
        if not src or not Path(src).is_file():
            QMessageBox.warning(self, "OCR", "Escolha um arquivo PDF válido.")
            return
        out = _ask_save_pdf(self, "Salvar PDF com OCR",
                            str(Path(src).with_name(Path(src).stem + "_ocr.pdf")))
        if not out:
            return
        lang, dpi = self.lang.currentData(), self.dpi.value()

        def done(_):
            self.result_path = out
            QMessageBox.information(self, "OCR", f"PDF pesquisável criado:\n{out}")
            self.accept()

        self.start(lambda prog: ops.ocr_pdf(src, out, lang, dpi, prog), done)


# ==========================================================================
# Criar PDF
# ==========================================================================
class CreateDialog(PolishedDialog):
    SIZES = [("A4", "a4"), ("A3", "a3"), ("A5", "a5"), ("Carta (Letter)", "letter"),
             ("Ofício (Legal)", "legal")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Criar PDF")
        self.setMinimumWidth(520)
        self.data: bytes | None = None
        self.name = "Sem título.pdf"
        v = QVBoxLayout(self)

        self.r_blank = QRadioButton("Página em branco")
        self.r_blank.setChecked(True)
        self.r_images = QRadioButton("A partir de imagens")
        v.addWidget(self.r_blank)
        self.blank_box = QWidget()
        f = QFormLayout(self.blank_box)
        self.size = QComboBox()
        for label, code in self.SIZES:
            self.size.addItem(label, code)
        self.orient = QComboBox()
        self.orient.addItems(["Retrato", "Paisagem"])
        self.pages = QSpinBox()
        self.pages.setRange(1, 500)
        f.addRow("Tamanho:", self.size)
        f.addRow("Orientação:", self.orient)
        f.addRow("Páginas:", self.pages)
        v.addWidget(self.blank_box)

        v.addWidget(self.r_images)
        self.img_box = QWidget()
        iv = QVBoxLayout(self.img_box)
        iv.setContentsMargins(0, 0, 0, 0)
        self.images = FileList(exts=IMG_EXTS,
                               filt="Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        iv.addWidget(self.images)
        self.img_box.setVisible(False)
        v.addWidget(self.img_box)
        self.r_blank.toggled.connect(self._toggle)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Criar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _toggle(self, blank: bool) -> None:
        self.blank_box.setVisible(blank)
        self.img_box.setVisible(not blank)

    def _create(self) -> None:
        try:
            if self.r_blank.isChecked():
                self.data = ops.blank_pdf(self.size.currentData(),
                                          self.orient.currentIndex() == 1, self.pages.value())
            else:
                files = self.images.files()
                if not files:
                    QMessageBox.warning(self, "Criar PDF", "Adicione ao menos uma imagem.")
                    return
                self.data = ops.images_to_pdf(files)
                self.name = Path(files[0]).stem + ".pdf"
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", str(exc))
            return
        self.accept()


# ==========================================================================
# Organizar páginas
# ==========================================================================
class OrganizeDialog(PolishedDialog):
    THUMB_W = 130

    def __init__(self, doc: "fitz.Document", src_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Organizar páginas")
        self.resize(900, 640)
        self.sources = [doc]
        self.src_path = src_path
        self.result_path: str | None = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Arraste as miniaturas para reordenar. Selecione várias com Ctrl/Shift."))

        bar = QHBoxLayout()
        for text, slot in (("↺ Girar", lambda: self._rotate(-90)), ("↻ Girar", lambda: self._rotate(90)),
                           ("Duplicar", self._duplicate), ("Excluir", self._delete),
                           ("＋ Página em branco", self._insert_blank),
                           ("＋ Inserir de PDF…", self._insert_pdf)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        v.addLayout(bar)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ListMode)  # ListMode + wrapping reordena de verdade
        self.list.setFlow(QListWidget.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setIconSize(QSize(self.THUMB_W, int(self.THUMB_W * 1.42)))
        self.list.setSpacing(8)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setMovement(QListWidget.Snap)
        self.list.model().rowsMoved.connect(lambda *_: self._renumber())
        v.addWidget(self.list, 1)

        self.count_lbl = QLabel()
        bottom = QHBoxLayout()
        bottom.addWidget(self.count_lbl)
        bottom.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        bottom.addWidget(_primary("Salvar como…", self._save))
        v.addLayout(bottom)

        self.setCursor(Qt.WaitCursor)
        for pno in range(doc.page_count):
            self.list.addItem(self._make_item(0, pno))
        self.unsetCursor()
        self._renumber()

    # ---- miniaturas ------------------------------------------------------
    def _thumb(self, d: dict) -> QPixmap:
        if d["blank"]:
            w, h = d["blank"]
            pm = QPixmap(self.THUMB_W, max(1, int(self.THUMB_W * h / w)))
            pm.fill(Qt.white)
        else:
            page = self.sources[d["src"]][d["pno"]]
            s = self.THUMB_W / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pm = QPixmap.fromImage(img)
        if d["rot"]:
            pm = pm.transformed(QTransform().rotate(d["rot"]), Qt.SmoothTransformation)
        return pm

    def _refresh_item(self, item: QListWidgetItem) -> None:
        item.setIcon(QIcon(self._thumb(item.data(Qt.UserRole))))

    def _make_item(self, src: int, pno: int, rot: int = 0, blank=None) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, {"src": src, "pno": pno, "rot": rot, "blank": blank})
        item.setTextAlignment(Qt.AlignHCenter)
        self._refresh_item(item)
        return item

    def _renumber(self) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setText(str(i + 1))
        self.count_lbl.setText(f"{self.list.count()} página(s)")

    # ---- ações -------------------------------------------------------------
    def _selected(self) -> list[QListWidgetItem]:
        return sorted(self.list.selectedItems(), key=self.list.row)

    def _insert_row(self) -> int:
        sel = self._selected()
        return self.list.row(sel[-1]) + 1 if sel else self.list.count()

    def _rotate(self, delta: int) -> None:
        for item in self._selected():
            d = dict(item.data(Qt.UserRole))
            d["rot"] = (d["rot"] + delta) % 360
            item.setData(Qt.UserRole, d)
            self._refresh_item(item)

    def _delete(self) -> None:
        for item in self._selected():
            self.list.takeItem(self.list.row(item))
        self._renumber()

    def _duplicate(self) -> None:
        row = self._insert_row()
        for item in self._selected():
            d = dict(item.data(Qt.UserRole))
            self.list.insertItem(row, self._make_item(d["src"], d["pno"], d["rot"], d["blank"]))
            row += 1
        self._renumber()

    def _insert_blank(self) -> None:
        ref = self.sources[0][0].rect if self.sources[0].page_count else fitz.paper_rect("a4")
        self.list.insertItem(self._insert_row(),
                             self._make_item(0, 0, 0, (ref.width, ref.height)))
        self._renumber()

    def _insert_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Inserir páginas de…", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            other = ops.open_pdf(path)
        except ops.PasswordRequired as exc:
            QMessageBox.warning(self, "Inserir", str(exc))
            return
        self.sources.append(other)
        idx, row = len(self.sources) - 1, self._insert_row()
        self.setCursor(Qt.WaitCursor)
        for pno in range(other.page_count):
            self.list.insertItem(row + pno, self._make_item(idx, pno))
        self.unsetCursor()
        self._renumber()

    def _save(self) -> None:
        if self.list.count() == 0:
            QMessageBox.warning(self, "Organizar", "O documento ficaria sem páginas.")
            return
        default = str(Path(self.src_path).with_name(Path(self.src_path).stem + "_organizado.pdf"))
        out = _ask_save_pdf(self, "Salvar PDF organizado", default)
        if not out:
            return
        items = []
        for i in range(self.list.count()):
            d = self.list.item(i).data(Qt.UserRole)
            items.append({"src": self.sources[d["src"]], "pno": d["pno"],
                          "rot": d["rot"], "blank": d["blank"]})
        try:
            ops.build_from_items(items, out)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", str(exc))
            return
        self.result_path = out
        self.accept()

    def done(self, r: int) -> None:  # noqa: D102
        for s in self.sources:
            s.close()
        super().done(r)


# ==========================================================================
# Formulários
# ==========================================================================
class FormDialog(PolishedDialog):
    def __init__(self, doc: "fitz.Document", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preencher formulário")
        self.resize(520, 560)
        v = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        self.fields: list[tuple] = []  # (page, widget, editor, kind)

        for pno in range(doc.page_count):
            page = doc[pno]
            for w in page.widgets():
                label = f"{w.field_label or w.field_name} (pág. {pno + 1})"
                t = w.field_type
                if t in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                    ed, kind = QCheckBox(), "check"
                    val = w.field_value
                    ed.setChecked(val is True or (isinstance(val, str) and val not in ("", "Off", "False")))
                elif t in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
                    ed, kind = QComboBox(), "choice"
                    ed.addItems([str(c) for c in (w.choice_values or [])])
                    ed.setCurrentText(str(w.field_value or ""))
                elif t == fitz.PDF_WIDGET_TYPE_TEXT:
                    ed, kind = QLineEdit(str(w.field_value or "")), "text"
                else:
                    continue  # botões e assinaturas digitais
                form.addRow(label, ed)
                self.fields.append((page, w, ed, kind))

        if not self.fields:
            form.addRow(QLabel("Nenhum campo preenchível encontrado."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def apply(self) -> None:
        for _page, w, ed, kind in self.fields:
            try:
                if kind == "check":
                    w.field_value = bool(ed.isChecked())
                elif kind == "choice":
                    w.field_value = ed.currentText()
                else:
                    w.field_value = ed.text()
                w.update()
            except Exception:  # noqa: BLE001 - um campo problemático não derruba os outros
                continue


# ==========================================================================
# Assinatura
# ==========================================================================
class SignatureCanvas(QWidget):
    PEN = QColor("#1a237e")

    def __init__(self):
        super().__init__()
        self.setFixedSize(520, 200)
        self.strokes: list[list[QPointF]] = []
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.white)
        p.setPen(QPen(QColor("#cccccc"), 1, Qt.DashLine))
        p.drawLine(20, self.height() - 50, self.width() - 20, self.height() - 50)
        self._draw(p)

    def _draw(self, p: QPainter) -> None:
        p.setPen(QPen(self.PEN, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            path = QPainterPath(s[0])
            for pt in s[1:]:
                path.lineTo(pt)
            if len(s) == 1:
                path.lineTo(s[0] + QPointF(0.1, 0.1))
            p.drawPath(path)

    def mousePressEvent(self, e):  # noqa: N802
        self.strokes.append([e.position()])

    def mouseMoveEvent(self, e):  # noqa: N802
        if self.strokes and e.buttons() & Qt.LeftButton:
            self.strokes[-1].append(e.position())
            self.update()

    def clear(self) -> None:
        self.strokes.clear()
        self.update()

    def to_png(self) -> bytes | None:
        pts = [pt for s in self.strokes for pt in s]
        if not pts:
            return None
        xs, ys = [p.x() for p in pts], [p.y() for p in pts]
        m = 6
        box = QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)
        img = QImage(int(box.width()) + 1, int(box.height()) + 1, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(-box.topLeft())
        self._draw(p)
        p.end()
        return _qimage_png(img)


def _qimage_png(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


class SignatureDialog(PolishedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Criar assinatura")
        self.png: bytes | None = None
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Desenhe sua assinatura com o mouse (ou use uma imagem):"))
        self.canvas = SignatureCanvas()
        v.addWidget(self.canvas)
        row = QHBoxLayout()
        clear = QPushButton("Limpar")
        clear.clicked.connect(self.canvas.clear)
        load = QPushButton("Usar imagem…")
        load.clicked.connect(self._load)
        row.addWidget(clear)
        row.addWidget(load)
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addWidget(_primary("Usar assinatura", self._ok))
        v.addLayout(row)

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Imagem da assinatura", "",
                                              "Imagens (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.png = Path(path).read_bytes()
            self.accept()

    def _ok(self) -> None:
        self.png = self.canvas.to_png()
        if self.png is None:
            QMessageBox.warning(self, "Assinatura", "Desenhe a assinatura primeiro.")
            return
        self.accept()


# ==========================================================================
# Editar parágrafo
# ==========================================================================
class ParagraphEditDialog(PolishedDialog):
    FAMILIES = [("Original do documento", "original"), ("Sem serifa (Helvetica/Arial)", "sans"),
                ("Com serifa (Times)", "serif"), ("Monoespaçada (Courier)", "mono")]
    ALIGNS = [("Esquerda", "left"), ("Centralizado", "center"), ("Direita", "right"),
              ("Justificado", "justify")]

    def __init__(self, block: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar parágrafo")
        self.resize(560, 460)
        self.color = tuple(block["color"])
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Fonte detectada: <b>{block['font']}</b> · {block['size']:.1f} pt · "
                           f"{block['nlines']} linha(s). O texto será refluído na largura original."))
        self.text = QPlainTextEdit(block["text"])
        v.addWidget(self.text, 1)

        form = QFormLayout()
        self.family = QComboBox()
        for label, key in self.FAMILIES:
            self.family.addItem(label, key)
        self.size = QDoubleSpinBox()
        self.size.setRange(4, 200)
        self.size.setDecimals(1)
        self.size.setValue(block["size"])
        self.size.setSuffix(" pt")
        self.bold = QCheckBox("Negrito")
        self.bold.setChecked(bool(block["flags"] & 16))
        self.italic = QCheckBox("Itálico")
        self.italic.setChecked(bool(block["flags"] & 2))
        style = QHBoxLayout()
        style.addWidget(self.bold)
        style.addWidget(self.italic)
        style.addStretch(1)
        self.align = QComboBox()
        for label, key in self.ALIGNS:
            self.align.addItem(label, key)
        self.align.setCurrentIndex([k for _l, k in self.ALIGNS].index(block["align"]))
        self.color_btn = QPushButton("Cor…")
        self.color_btn.clicked.connect(self._pick_color)
        self._paint_color_btn()
        form.addRow("Fonte:", self.family)
        form.addRow("Tamanho:", self.size)
        form.addRow("Estilo:", style)
        form.addRow("Alinhamento:", self.align)
        form.addRow("Cor:", self.color_btn)
        v.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _paint_color_btn(self) -> None:
        r, g, b = (int(c * 255) for c in self.color)
        self.color_btn.setStyleSheet(f"background: rgb({r},{g},{b}); color: "
                                     f"{'#000' if r + g + b > 380 else '#fff'};")

    def _pick_color(self) -> None:
        r, g, b = (int(c * 255) for c in self.color)
        c = QColorDialog.getColor(QColor(r, g, b), self, "Cor do texto")
        if c.isValid():
            self.color = (c.redF(), c.greenF(), c.blueF())
            self._paint_color_btn()

    def values(self) -> dict:
        return {"new_text": self.text.toPlainText().rstrip(), "family": self.family.currentData(),
                "size": self.size.value(), "bold": self.bold.isChecked(),
                "italic": self.italic.isChecked(), "color": self.color,
                "align": self.align.currentData()}


# ==========================================================================
# Carimbos
# ==========================================================================
STAMPS = [("APROVADO", "#1b8a3a"), ("REPROVADO", "#c62828"), ("CONFIDENCIAL", "#c62828"),
          ("RASCUNHO", "#546e7a"), ("URGENTE", "#e65100"), ("REVISADO", "#1565c0"),
          ("CÓPIA", "#546e7a"), ("PAGO", "#1b8a3a")]


def make_stamp_png(text: str, color: str) -> bytes:
    font = QFont("Segoe UI", 28)
    font.setBold(True)
    fm = QFontMetrics(font)
    w, h = fm.horizontalAdvance(text) + 56, fm.height() + 28
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 6)
    p.setPen(pen)
    p.drawRoundedRect(QRectF(5, 5, w - 10, h - 10), 14, 14)
    p.setFont(font)
    p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, text)
    p.end()
    return _qimage_png(img.transformed(QTransform().rotate(-7), Qt.SmoothTransformation))


# ==========================================================================
# Assinatura digital com certificado
# ==========================================================================
class CertCreateDialog(PolishedDialog):
    """Cria um certificado .pfx autoassinado (para testes / uso interno)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Criar certificado autoassinado")
        self.setMinimumWidth(480)
        self.path = ""
        v = QVBoxLayout(self)
        note = QLabel("Certificados autoassinados provam que o arquivo não foi alterado, mas "
                      "<b>não</b> provam sua identidade para terceiros (não são confiáveis por padrão). "
                      "Para validade jurídica use um certificado de uma autoridade (ex.: ICP-Brasil).")
        note.setWordWrap(True)
        v.addWidget(note)
        form = QFormLayout()
        self.name = QLineEdit()
        self.email = QLineEdit()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.out = PathPicker("save", "Salvar certificado", "Certificado (*.pfx *.p12)", "meu_certificado.pfx")
        form.addRow("Nome:", self.name)
        form.addRow("E-mail (opcional):", self.email)
        form.addRow("Senha do certificado:", self.pw)
        form.addRow("Confirmar senha:", self.pw2)
        form.addRow("Salvar em:", self.out)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addWidget(_primary("Criar", self._create))
        v.addLayout(row)

    def _create(self) -> None:
        import signing
        if not self.name.text().strip() or not self.pw.text() or not self.out.text():
            QMessageBox.warning(self, "Certificado", "Informe nome, senha e onde salvar.")
            return
        if self.pw.text() != self.pw2.text():
            QMessageBox.warning(self, "Certificado", "As senhas não conferem.")
            return
        path = self.out.text()
        if not path.lower().endswith((".pfx", ".p12")):
            path += ".pfx"
        try:
            signing.create_self_signed(path, self.pw.text(), self.name.text().strip(), self.email.text().strip())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", str(exc))
            return
        self.path = path
        self.accept()


class CertSignDialog(PolishedDialog):
    POSITIONS = ["Canto inferior direito", "Canto inferior esquerdo", "Centro inferior", "Canto superior direito"]

    def __init__(self, page_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assinar digitalmente")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Assinatura digital com certificado (.pfx / .p12). Após assinar, "
                           "qualquer alteração no arquivo invalida a assinatura."))
        form = QFormLayout()
        self.cert = PathPicker("open", "Escolher certificado", "Certificado (*.pfx *.p12)", "Arquivo .pfx / .p12")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Ex.: Aprovação do contrato")
        self.location = QLineEdit()
        self.visible = QCheckBox("Mostrar carimbo visível na página")
        self.page = QSpinBox()
        self.page.setRange(1, max(1, page_count))
        self.page.setValue(max(1, page_count))
        self.pos = QComboBox()
        self.pos.addItems(self.POSITIONS)
        form.addRow("Certificado:", self.cert)
        form.addRow("Senha:", self.pw)
        form.addRow("Motivo:", self.reason)
        form.addRow("Local:", self.location)
        form.addRow("", self.visible)
        form.addRow("Página:", self.page)
        form.addRow("Posição:", self.pos)
        v.addLayout(form)
        self.visible.toggled.connect(lambda on: (self.page.setEnabled(on), self.pos.setEnabled(on)))
        self.page.setEnabled(False)
        self.pos.setEnabled(False)

        row = QHBoxLayout()
        create = QPushButton("Criar certificado de teste…")
        create.clicked.connect(self._create_cert)
        row.addWidget(create)
        row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addWidget(_primary("Assinar e salvar…", self._ok))
        v.addLayout(row)

    def _create_cert(self) -> None:
        dlg = CertCreateDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.cert.setText(dlg.path)

    def _ok(self) -> None:
        if not self.cert.text() or not Path(self.cert.text()).is_file():
            QMessageBox.warning(self, "Assinatura", "Escolha o arquivo do certificado.")
            return
        self.accept()

    def values(self) -> dict:
        return {"pfx": self.cert.text(), "password": self.pw.text(), "reason": self.reason.text().strip(),
                "location": self.location.text().strip(), "visible": self.visible.isChecked(),
                "page": self.page.value() - 1, "position": self.pos.currentIndex()}


def show_verification(parent, results: list[dict]) -> None:
    if not results:
        QMessageBox.information(parent, "Assinaturas", "Este PDF não possui assinaturas digitais.")
        return
    rows = []
    for r in results:
        if "error" in r:
            rows.append(f"<p>❌ <b>{r['field']}</b><br>Não foi possível validar: {r['error']}</p>")
            continue
        ok = r["intact"] and r["valid"]
        icon = "✅" if ok else "❌"
        lines = [f"{icon} <b>{r['field']}</b> — {r['signer']}"]
        lines.append("Integridade: " + ("documento NÃO foi alterado após a assinatura"
                                         if r["intact"] else "<b>o documento foi alterado após a assinatura</b>"))
        if not r["whole_doc"] and r["intact"]:
            lines.append("Atenção: há conteúdo adicionado depois desta assinatura (outra assinatura ou edição).")
        lines.append("Emissor: " + ("certificado confiável neste computador" if r["trusted"]
                                    else "<b>não verificado</b> (autoassinado ou emissor desconhecido)"))
        if r.get("date"):
            lines.append(f"Data informada pelo signatário: {r['date']:%d/%m/%Y %H:%M} UTC")
        if r.get("reason"):
            lines.append(f"Motivo: {r['reason']}")
        rows.append("<p>" + "<br>".join(lines) + "</p>")
    QMessageBox.information(parent, "Assinaturas digitais", "".join(rows))


# --------------------------------------------------------------------------
# Ferramentas de página: marca d'água, cabeçalho/rodapé, localizar/substituir, recorte, extração
# --------------------------------------------------------------------------
class _ColorButton(QPushButton):
    def __init__(self, color: str = "#000000"):
        super().__init__()
        self._color = QColor(color)
        self.setFixedWidth(64)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self) -> None:
        self.setText(self._color.name().upper())

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "Escolher cor")
        if c.isValid():
            self._color = c
            self._paint()

    def rgb(self) -> tuple[float, float, float]:
        return (self._color.redF(), self._color.greenF(), self._color.blueF())


def _buttons(dlg: QDialog, ok_text: str) -> QDialogButtonBox:
    box = QDialogButtonBox()
    ok = box.addButton(ok_text, QDialogButtonBox.AcceptRole)
    ok.setObjectName("primary")
    box.addButton("Cancelar", QDialogButtonBox.RejectRole)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


class WatermarkDialog(PolishedDialog):
    def __init__(self, page_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Marca d'água")
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.text = QLineEdit("CONFIDENCIAL")
        self.size = QSpinBox(); self.size.setRange(12, 300); self.size.setValue(80); self.size.setSuffix(" pt")
        self.angle = QSpinBox(); self.angle.setRange(-90, 90); self.angle.setValue(45); self.angle.setSuffix("°")
        self.opacity = QSpinBox(); self.opacity.setRange(5, 100); self.opacity.setValue(25); self.opacity.setSuffix(" %")
        self.color = _ColorButton("#808080")
        self.pages = QLineEdit(); self.pages.setPlaceholderText(f"Todas (1–{page_count}) — ou ex.: 1-3, 5")
        self.behind = QCheckBox("Colocar atrás do conteúdo")
        form.addRow("Texto:", self.text)
        form.addRow("Tamanho:", self.size)
        form.addRow("Inclinação:", self.angle)
        form.addRow("Opacidade:", self.opacity)
        form.addRow("Cor:", self.color)
        form.addRow("Páginas:", self.pages)
        form.addRow("", self.behind)
        v.addLayout(form)
        v.addWidget(_buttons(self, "Aplicar"))

    def values(self) -> dict:
        return {"text": self.text.text(), "size": self.size.value(), "angle": self.angle.value(),
                "opacity": self.opacity.value() / 100, "color": self.color.rgb(),
                "pages": self.pages.text().strip() or None, "behind": self.behind.isChecked()}


class HeaderFooterDialog(PolishedDialog):
    def __init__(self, page_count: int, preset: str = "header", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Número de página" if preset == "number" else "Cabeçalho e rodapé")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Use {n} (nº da página), {total}, {data} e {arquivo} nos textos."))
        grid = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        for key, label in (("tl", "Cabeçalho — esquerda"), ("tc", "Cabeçalho — centro"), ("tr", "Cabeçalho — direita"),
                           ("bl", "Rodapé — esquerda"), ("bc", "Rodapé — centro"), ("br", "Rodapé — direita")):
            e = QLineEdit()
            self.fields[key] = e
            grid.addRow(label + ":", e)
        if preset == "number":
            self.fields["bc"].setText("Página {n} de {total}")
        v.addLayout(grid)
        opts = QFormLayout()
        self.size = QSpinBox(); self.size.setRange(6, 36); self.size.setValue(10); self.size.setSuffix(" pt")
        self.margin = QSpinBox(); self.margin.setRange(8, 120); self.margin.setValue(28); self.margin.setSuffix(" pt")
        self.color = _ColorButton("#333333")
        self.start = QSpinBox(); self.start.setRange(0, 99999); self.start.setValue(1)
        self.pages = QLineEdit(); self.pages.setPlaceholderText(f"Todas (1–{page_count}) — ou ex.: 2-")
        opts.addRow("Tamanho:", self.size)
        opts.addRow("Margem da borda:", self.margin)
        opts.addRow("Cor:", self.color)
        opts.addRow("Numerar a partir de:", self.start)
        opts.addRow("Páginas:", self.pages)
        v.addLayout(opts)
        v.addWidget(_buttons(self, "Aplicar"))

    def values(self) -> dict:
        return {"texts": {k: e.text() for k, e in self.fields.items()}, "size": self.size.value(),
                "margin": self.margin.value(), "color": self.color.rgb(), "start": self.start.value(),
                "pages": self.pages.text().strip() or None}


class FindReplaceDialog(PolishedDialog):
    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Localizar e substituir")
        self.setMinimumWidth(440)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.find = QLineEdit(initial)
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("Vazio = remover o texto encontrado")
        self.case = QCheckBox("Diferenciar maiúsculas de minúsculas")
        form.addRow("Localizar:", self.find)
        form.addRow("Substituir por:", self.repl)
        form.addRow("", self.case)
        v.addLayout(form)
        note = QLabel("Cada ocorrência mantém a fonte, o tamanho e a cor originais. O restante da linha acompanha "
                      "a nova largura; ocorrências que invadiriam outra coluna ou a margem são puladas e contadas.")
        note.setWordWrap(True)
        note.setObjectName("dim")
        v.addWidget(note)
        v.addWidget(_buttons(self, "Substituir tudo"))
        self.find.setFocus()

    def values(self) -> dict:
        return {"query": self.find.text(), "repl": self.repl.text(), "case": self.case.isChecked()}


class CropDialog(PolishedDialog):
    def __init__(self, page_count: int, current: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recortar página")
        self.setMinimumWidth(380)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.m = {}
        for key, label in (("top", "Superior"), ("bottom", "Inferior"), ("left", "Esquerda"), ("right", "Direita")):
            s = QDoubleSpinBox(); s.setRange(0, 600); s.setDecimals(1); s.setSuffix(" pt")
            self.m[key] = s
            form.addRow(f"Margem {label.lower()}:", s)
        self.scope = QComboBox()
        self.scope.addItem(f"Somente a página {current}", str(current))
        self.scope.addItem("Todas as páginas", "")
        form.addRow("Aplicar a:", self.scope)
        v.addLayout(form)
        v.addWidget(QLabel("O recorte só esconde as bordas; o conteúdo continua no arquivo."))
        v.addWidget(_buttons(self, "Recortar"))

    def values(self) -> dict:
        return {**{k: s.value() for k, s in self.m.items()}, "pages": self.scope.currentData() or None}


class ExtractDialog(PolishedDialog):
    def __init__(self, page_count: int, current: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extrair páginas")
        self.setMinimumWidth(380)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Páginas a extrair para um novo PDF (documento tem {page_count}):"))
        self.spec = QLineEdit(str(current))
        self.spec.setPlaceholderText("ex.: 1-3, 5, 8-")
        v.addWidget(self.spec)
        v.addWidget(_buttons(self, "Extrair…"))

    def value(self) -> str:
        return self.spec.text().strip()


# --------------------------------------------------------------------------
# Atualização do aplicativo
# --------------------------------------------------------------------------
class UpdateDialog(TaskDialog):
    """Consulta a versão mais recente e, se houver, baixa e prepara a atualização (sem desinstalar)."""

    def __init__(self, current: str, url: str, parent=None, info: dict | None = None):
        super().__init__("Atualizações", parent)
        import updater
        self._u = updater
        self.current, self.url = current, url
        self.info = info
        self.installer_path: str | None = None
        self.title = QLabel()
        self.title.setObjectName("h2")
        self.title.setWordWrap(True)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(150)
        self.notes.hide()
        self.body.addWidget(self.title)
        self.body.addWidget(self.notes)
        self.go = _primary("Atualizar agora", self._download)
        self.go.hide()
        self.body.addWidget(self.go)
        self.setMinimumWidth(480)
        if info:
            self._show(info)
        else:
            self.title.setText("Procurando atualizações…")
            self.start(lambda prog: updater.fetch_latest(url), self._show, )

    def _fail(self, msg: str) -> None:  # noqa: D401 — erro do Worker
        super()._fail(msg)
        self.content.setEnabled(True)
        self.title.setText("Não foi possível verificar agora.")

    def _show(self, info) -> None:
        self.content.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText("")
        self.info = info
        if not self._u.is_newer(info["version"], self.current):
            self.title.setText(f"Você já está na versão mais recente ({self.current}).")
            return
        self.title.setText(f"Nova versão disponível: {info['version']}  (você tem {self.current})")
        if info.get("notes"):
            self.notes.setPlainText(info["notes"])
            self.notes.show()
        self.status.setText("A atualização é instalada por cima da atual: seus documentos, configurações, "
                            "recentes e preferências são mantidos.")
        self.go.show()

    def _download(self) -> None:
        self.go.setEnabled(False)

        def run(prog):
            return self._u.download(self.info, prog)

        def done(path):
            self.installer_path = path
            self.status.setText("Download concluído e verificado. O programa vai fechar, atualizar e reabrir.")
            self.accept()

        def failed(msg):
            self.go.setEnabled(True)
            self.content.setEnabled(True)
            self.progress.setVisible(False)
            QMessageBox.warning(self, "Atualização", msg)

        self.content.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("Baixando a atualização…")
        w = Worker(run, self)
        w.progress.connect(self._on_progress)
        w.done.connect(done)
        w.failed.connect(failed)
        self._worker = w
        w.start()


# --------------------------------------------------------------------------
# Arquivo › Propriedades do documento / Preferências
# --------------------------------------------------------------------------
def _pdf_date(raw: str) -> str:
    """'D:20260315143000+00'00'' -> '15/03/2026 14:30'."""
    import re
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?", raw or "")
    if not m:
        return raw or "—"
    y, mo, d, h, mi = (m.group(i) or "" for i in range(1, 6))
    out = f"{d or '01'}/{mo or '01'}/{y}"
    return out + (f" {h}:{mi or '00'}" if h else "")


class PropertiesDialog(PolishedDialog):
    def __init__(self, doc, path: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propriedades do documento")
        self.setMinimumWidth(520)
        meta = doc.metadata or {}
        v = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.fields: dict[str, QLineEdit] = {}
        for key, label in (("title", "Título"), ("author", "Autor"), ("subject", "Assunto"), ("keywords", "Palavras-chave")):
            e = QLineEdit(meta.get(key) or "")
            self.fields[key] = e
            form.addRow(label + ":", e)
        self._orig = {k: e.text() for k, e in self.fields.items()}

        def info(text: str) -> QLabel:
            lb = QLabel(text)
            lb.setObjectName("dim")
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lb.setWordWrap(True)
            return lb

        size_txt = "—"
        if path and Path(path).is_file():
            size_txt = ops.fmt_size(Path(path).stat().st_size)
        r = doc[0].rect if doc.page_count else None
        page_txt = f"{r.width:.0f} × {r.height:.0f} pt  ({r.width * 25.4 / 72:.0f} × {r.height * 25.4 / 72:.0f} mm)" if r else "—"
        form.addRow("Arquivo:", info(path or "(documento novo, ainda não salvo)"))
        form.addRow("Tamanho:", info(size_txt))
        form.addRow("Páginas:", info(str(doc.page_count)))
        form.addRow("Tamanho da página:", info(page_txt))
        form.addRow("Versão do PDF:", info(meta.get("format") or "—"))
        form.addRow("Protegido por senha:", info("Sim" if doc.is_encrypted else "Não"))
        form.addRow("Criado em:", info(_pdf_date(meta.get("creationDate", ""))))
        form.addRow("Modificado em:", info(_pdf_date(meta.get("modDate", ""))))
        form.addRow("Criado com:", info(meta.get("creator") or "—"))
        form.addRow("Gerado por:", info(meta.get("producer") or "—"))
        v.addLayout(form)
        v.addWidget(_buttons(self, "Aplicar"))

    def changes(self) -> dict | None:
        new = {k: e.text().strip() for k, e in self.fields.items()}
        old = {k: v.strip() for k, v in self._orig.items()}
        return new if new != old else None


class PreferencesDialog(PolishedDialog):
    def __init__(self, appearance: str, auto_update: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferências")
        self.setMinimumWidth(400)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.look = QComboBox()
        for label, key in (("Seguir o sistema", "system"), ("Claro", "light"), ("Escuro", "dark")):
            self.look.addItem(label, key)
        self.look.setCurrentIndex(max(0, self.look.findData(appearance)))
        form.addRow("Aparência:", self.look)
        self.auto = QCheckBox("Verificar atualizações automaticamente (uma vez por dia)")
        self.auto.setChecked(auto_update)
        form.addRow("", self.auto)
        v.addLayout(form)
        v.addWidget(_buttons(self, "Salvar"))

    def values(self) -> tuple[str, bool]:
        return self.look.currentData(), self.auto.isChecked()
