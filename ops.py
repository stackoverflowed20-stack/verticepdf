"""Operações de PDF do Vértice PDF (sem dependência de interface gráfica).

Todas as funções abrem os arquivos a partir de bytes na memória, assim o
Windows não mantém o arquivo travado e é possível salvar por cima do original.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24.3
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

Progress = Optional[Callable[[int, int], None]]


class PasswordRequired(Exception):
    """O PDF está protegido por senha (ou a senha está errada)."""


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _tick(cb: Progress, cur: int, total: int) -> None:
    if cb:
        cb(cur, total)


def write_file(path: str | Path, data: bytes) -> None:
    """Grava de forma atômica (arquivo temporário + replace)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def open_pdf(path: str | Path, password: str | None = None) -> "fitz.Document":
    doc = fitz.open(stream=Path(path).read_bytes(), filetype="pdf")
    if doc.needs_pass and not (password and doc.authenticate(password)):
        doc.close()
        raise PasswordRequired(f"'{Path(path).name}' está protegido por senha.")
    return doc


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def parse_ranges(spec: str, n: int) -> list[tuple[int, int]]:
    """'1-3, 5, 7-' -> [(0, 2), (4, 4), (6, n-1)]  (índices base 0, inclusivos)."""
    groups: list[tuple[int, int]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else n
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"Intervalo inválido: '{part}'")
        if a < 1 or b > n or a > b:
            raise ValueError(f"Intervalo fora do documento (1–{n}): '{part}'")
        groups.append((a - 1, b - 1))
    if not groups:
        raise ValueError("Informe ao menos um intervalo, ex.: 1-3, 5, 7-9")
    return groups


def groups_every(n: int, k: int) -> list[tuple[int, int]]:
    k = max(1, k)
    return [(i, min(i + k - 1, n - 1)) for i in range(0, n, k)]


# --------------------------------------------------------------------------
# Combinar / dividir / converter
# --------------------------------------------------------------------------
def merge(paths: list[str], out: str, progress: Progress = None) -> str:
    result = fitz.open()
    try:
        for i, p in enumerate(paths):
            with open_pdf(p) as d:
                result.insert_pdf(d)
            _tick(progress, i + 1, len(paths))
        write_file(out, result.tobytes(garbage=3, deflate=True))
    finally:
        result.close()
    return out


def split(path: str, groups: list[tuple[int, int]], outdir: str,
          progress: Progress = None) -> list[str]:
    outdir_p = Path(outdir)
    outdir_p.mkdir(parents=True, exist_ok=True)
    outs: list[str] = []
    with open_pdf(path) as src:
        width = len(str(len(groups)))
        for i, (a, b) in enumerate(groups, 1):
            part = fitz.open()
            part.insert_pdf(src, from_page=a, to_page=b)
            out = outdir_p / f"{Path(path).stem}_parte{i:0{width}d}.pdf"
            write_file(out, part.tobytes(garbage=3, deflate=True))
            part.close()
            outs.append(str(out))
            _tick(progress, i, len(groups))
    return outs


def to_images(path: str, outdir: str, fmt: str = "png", dpi: int = 150) -> int:
    Path(outdir).mkdir(parents=True, exist_ok=True)
    with open_pdf(path) as doc:
        width = len(str(doc.page_count))
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            pix.save(str(Path(outdir) / f"pagina_{i:0{width}d}.{fmt}"))
        return doc.page_count


def to_text(path: str, out: str) -> int:
    with open_pdf(path) as doc:
        chunks = [f"--- Página {i} ---\n{p.get_text()}" for i, p in enumerate(doc, 1)]
        Path(out).write_text("\n".join(chunks), encoding="utf-8")
        return doc.page_count


def images_to_pdf(paths: list[str]) -> bytes:
    result = fitz.open()
    for p in paths:
        with fitz.open(p) as img:
            result.insert_pdf(fitz.open("pdf", img.convert_to_pdf()))
    data = result.tobytes(garbage=3, deflate=True)
    result.close()
    return data


def blank_pdf(size: str = "a4", landscape: bool = False, pages: int = 1) -> bytes:
    w, h = fitz.paper_size(size)
    if landscape:
        w, h = h, w
    doc = fitz.open()
    for _ in range(max(1, pages)):
        doc.new_page(width=w, height=h)
    data = doc.tobytes()
    doc.close()
    return data


# --------------------------------------------------------------------------
# Compressão e segurança
# --------------------------------------------------------------------------
_LEVELS = {"leve": None, "media": (150, 75), "forte": (96, 50)}


def compress(path: str, out: str, level: str = "media") -> tuple[int, int]:
    """Retorna (tamanho_antes, tamanho_depois)."""
    before = os.path.getsize(path)
    doc = open_pdf(path)
    try:
        params = _LEVELS[level]
        if params:
            dpi, quality = params
            try:
                doc.rewrite_images(dpi_threshold=dpi + 30, dpi_target=dpi, quality=quality)
            except Exception:
                pass  # versões antigas / imagens exóticas: segue só com a limpeza
        data = doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
    if len(data) >= before:  # nunca devolve um arquivo maior que o original
        data = Path(path).read_bytes()
    write_file(out, data)
    return before, len(data)


def encrypt(path: str, out: str, user_pw: str, owner_pw: str = "",
            allow_print: bool = True, allow_copy: bool = True,
            allow_edit: bool = False, password: str | None = None) -> None:
    perm = fitz.PDF_PERM_ACCESSIBILITY
    if allow_print:
        perm |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
    if allow_copy:
        perm |= fitz.PDF_PERM_COPY
    if allow_edit:
        perm |= (fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE
                 | fitz.PDF_PERM_FORM | fitz.PDF_PERM_ASSEMBLE)
    with open_pdf(path, password) as doc:
        data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user_pw,
                           owner_pw=owner_pw or user_pw, permissions=perm,
                           garbage=3, deflate=True)
    write_file(out, data)


def decrypt(path: str, out: str, password: str) -> None:
    with open_pdf(path, password) as doc:
        data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    write_file(out, data)


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------
def _app_dir() -> Path:
    """Pasta do programa (a do .exe quando empacotado)."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def find_tesseract() -> str | None:
    """Tesseract embutido pelo instalador (pasta 'tesseract') ou instalado no sistema."""
    for name in ("tesseract.exe", "tesseract"):
        bundled = _app_dir() / "tesseract" / name
        if bundled.is_file():
            return str(bundled)
    found = shutil.which("tesseract")
    if found:
        return found
    for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(cand):
            return cand
    return None


def ocr_pdf(path: str, out: str, lang: str = "por+eng", dpi: int = 200,
            progress: Progress = None) -> str:
    """Gera um PDF pesquisável (camada de texto invisível sobre a imagem)."""
    import io

    import pytesseract
    from PIL import Image

    exe = find_tesseract()
    if not exe:
        raise RuntimeError("Tesseract não encontrado. Instale-o (veja o README).")
    pytesseract.pytesseract.tesseract_cmd = exe
    bundled_data = Path(exe).parent / "tessdata"
    if bundled_data.is_dir():  # Tesseract embutido: usa os idiomas que vieram junto
        os.environ["TESSDATA_PREFIX"] = str(bundled_data)

    installed = set(pytesseract.get_languages(config=""))
    wanted = [l for l in lang.split("+") if l in installed]
    if not wanted:
        raise RuntimeError(
            f"Idioma '{lang}' não instalado no Tesseract. "
            f"Instalados: {', '.join(sorted(installed)) or 'nenhum'}")

    src = open_pdf(path)
    result = fitz.open()
    try:
        for i, page in enumerate(src, 1):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_pdf = pytesseract.image_to_pdf_or_hocr(
                img, lang="+".join(wanted), extension="pdf")
            with fitz.open("pdf", page_pdf) as ocr_doc:
                new = result.new_page(width=page.rect.width, height=page.rect.height)
                new.show_pdf_page(new.rect, ocr_doc, 0)
            _tick(progress, i, src.page_count)
        write_file(out, result.tobytes(garbage=3, deflate=True))
    finally:
        src.close()
        result.close()
    return out


# --------------------------------------------------------------------------
# Organizar páginas
# --------------------------------------------------------------------------
def build_from_items(items: list[dict], out: str) -> None:
    """items: {'src': Document, 'pno': int, 'rot': int} ou {'blank': (w, h)}."""
    new = fitz.open()
    try:
        for it in items:
            if it.get("blank"):
                w, h = it["blank"]
                page = new.new_page(width=w, height=h)
            else:
                new.insert_pdf(it["src"], from_page=it["pno"], to_page=it["pno"])
                page = new[new.page_count - 1]
            if it.get("rot"):
                page.set_rotation((page.rotation + it["rot"]) % 360)
        write_file(out, new.tobytes(garbage=3, deflate=True))
    finally:
        new.close()


# --------------------------------------------------------------------------
# Edição dentro de uma página
# (os pontos/retângulos chegam em coordenadas da página como exibida,
#  ou seja, já com a rotação aplicada; convertemos aqui.)
# --------------------------------------------------------------------------
def _pt(page, pt) -> "fitz.Point":
    return fitz.Point(pt) * page.derotation_matrix


def _rect(page, r) -> "fitz.Rect":
    return fitz.Rect(r).transform(page.derotation_matrix)


def add_text(page, pt, text: str, size: float = 12, color=(0, 0, 0)) -> None:
    p = _pt(page, pt)
    box = fitz.Rect(p.x, p.y, max(p.x + 60, page.rect.x1 - 20), page.rect.y1 - 10)
    rc = page.insert_textbox(box, text, fontsize=size, fontname="helv",
                             color=color, rotate=page.rotation)
    if rc < 0:  # não coube na caixa: escreve linha a linha
        for k, line in enumerate(text.split("\n")):
            page.insert_text((p.x, p.y + size * 1.2 * (k + 1)), line,
                             fontsize=size, fontname="helv", color=color)


def highlight(page, rect, color=(1, 0.9, 0)) -> None:
    r = _rect(page, rect)
    quads = [fitz.Rect(w[:4]).quad for w in page.get_text("words", clip=r)]
    if quads:
        annot = page.add_highlight_annot(quads=quads)
        annot.set_colors(stroke=color)
    else:  # sem texto embaixo (página escaneada): marca a área
        annot = page.add_rect_annot(r)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(0.4)
    annot.update()


def _sample_bg(page, disp_rect) -> tuple[float, float, float]:
    """Cor de fundo predominante nos cantos da área (coords. exibidas)."""
    try:
        r = fitz.Rect(disp_rect) & page.rect
        if r.is_empty:
            return (1, 1, 1)
        pix = page.get_pixmap(clip=r, dpi=72, alpha=False, annots=False)
        w, h = pix.width, pix.height
        corners = [pix.pixel(x, y) for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        best = max(set(corners), key=corners.count)
        return tuple(c / 255 for c in best[:3])
    except Exception:  # noqa: BLE001 - cai para branco
        return (1, 1, 1)


def erase(page, rect) -> None:
    fill = _sample_bg(page, rect)
    page.add_redact_annot(_rect(page, rect), fill=fill)
    page.apply_redactions()


def add_image(page, rect, png: bytes) -> None:
    page.insert_image(_rect(page, rect), stream=png, keep_proportion=True, overlay=True)


_FONTS = {
    "sans": {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"},
    "serif": {(0, 0): "tiro", (1, 0): "tibo", (0, 1): "tiit", (1, 1): "tibi"},
    "mono": {(0, 0): "cour", (1, 0): "cobo", (0, 1): "coit", (1, 1): "cobi"},
}


def _base14(flags: int) -> str:
    family = "mono" if flags & 8 else "serif" if flags & 4 else "sans"
    return _FONTS[family][(1 if flags & 16 else 0, 1 if flags & 2 else 0)]


def line_at(page, pt) -> dict | None:
    """Linha de texto sob o ponto (coordenadas exibidas), ou None."""
    p = _pt(page, pt)
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if spans and fitz.Rect(line["bbox"]).contains(p):
                first = spans[0]
                return {
                    "bbox": tuple(line["bbox"]),
                    "text": "".join(s["text"] for s in line["spans"]),
                    "size": first["size"],
                    "color": fitz.sRGB_to_pdf(first["color"]),
                    "flags": first["flags"],
                    "origin": tuple(first["origin"]),
                }
    return None


def replace_line(page, line: dict, new_text: str) -> None:
    """Troca o texto de uma linha (cobre o original com a cor de fundo e reescreve)."""
    disp = fitz.Rect(line["bbox"]).transform(page.rotation_matrix)
    fill = _sample_bg(page, disp)
    page.add_redact_annot(fitz.Rect(line["bbox"]), fill=fill)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    page.insert_text(line["origin"], new_text, fontsize=line["size"],
                     fontname=_base14(line["flags"]), color=line["color"],
                     rotate=page.rotation)
