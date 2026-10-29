"""Exportação do PDF para Word (.docx), Excel (.xlsx), PowerPoint (.pptx) e imagens.

Sem dependência de Qt nem de bibliotecas de Office: os formatos OOXML são gravados com `zipfile`
(o modelo vazio do PowerPoint vem de `_pptx_base`). Trabalha sobre o `fitz.Document` já aberto,
então inclui as edições ainda não salvas.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

Progress = Callable[[int, int], None] | None

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _x(text: str) -> str:
    return escape(_CTRL.sub("", text))


def _tick(progress: Progress, i: int, n: int) -> None:
    if progress:
        progress(i, n)


# ---- Word ------------------------------------------------------------------------------
def _run(span: dict) -> str:
    text = _x(span.get("text", ""))
    if not text.strip() and not text:
        return ""
    flags = span.get("flags", 0)
    props = []
    if flags & 16 or "bold" in span.get("font", "").lower():
        props.append("<w:b/>")
    if flags & 2 or "italic" in span.get("font", "").lower() or "oblique" in span.get("font", "").lower():
        props.append("<w:i/>")
    color = span.get("color", 0)
    if color:
        props.append(f'<w:color w:val="{color & 0xFFFFFF:06X}"/>')
    size = round(float(span.get("size", 11)) * 2)
    if 2 <= size <= 400:
        props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def export_docx(doc: "fitz.Document", path: str, progress: Progress = None) -> dict:
    """Um parágrafo por bloco de texto, mantendo tamanho, negrito, itálico e cor. Imagens não são levadas."""
    body: list[str] = []
    n = doc.page_count
    paragraphs = empty_pages = 0
    for i in range(n):
        _tick(progress, i, n)
        page = doc[i]
        data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        first = True
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            runs: list[str] = []
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if runs:
                    runs.append('<w:r><w:t xml:space="preserve"> </w:t></w:r>')
                runs.extend(r for r in (_run(s) for s in spans) if r)
            if not runs:
                continue
            ppr = "<w:pPr><w:pageBreakBefore/></w:pPr>" if first and i > 0 else ""
            body.append(f"<w:p>{ppr}{''.join(runs)}</w:p>")
            first = False
            paragraphs += 1
        if first:  # página sem texto (imagem/digitalizada): mantém a quebra de página
            empty_pages += 1
            ppr = "<w:pPr><w:pageBreakBefore/></w:pPr>" if i > 0 else ""
            body.append(f"<w:p>{ppr}</w:p>")
    r0 = doc[0].rect if n else fitz.Rect(0, 0, 595, 842)
    w, h = int(r0.width * 20), int(r0.height * 20)
    sect = (f'<w:sectPr><w:pgSz w:w="{w}" w:h="{h}"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    document = (_XML + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body>{"".join(body)}{sect}</w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", _XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
    _tick(progress, n, n)
    return {"paragraphs": paragraphs, "empty_pages": empty_pages, "pages": n}


# ---- Excel -----------------------------------------------------------------------------
_NUM = re.compile(r"^-?(0|[1-9]\d{0,14})(\.\d+)?$")


def _col(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def _sheet_xml(rows: list[list[str]]) -> str:
    out = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, val in enumerate(row):
            val = "" if val is None else str(val)
            if not val:
                continue
            ref = f"{_col(c)}{r}"
            if _NUM.match(val):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_x(val)}</t></is></c>')
        out.append(f'<row r="{r}">{"".join(cells)}</row>')
    return (_XML + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(out)}</sheetData></worksheet>')


def _sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31] or "Planilha"
    cand, k = base, 2
    while cand.lower() in used:
        suffix = f" ({k})"
        cand = base[:31 - len(suffix)] + suffix
        k += 1
    used.add(cand.lower())
    return cand


def export_xlsx(doc: "fitz.Document", path: str, progress: Progress = None) -> dict:
    """Cada tabela detectada vira uma planilha. Sem tabelas, o texto vai linha a linha em uma planilha 'Texto'."""
    sheets: list[tuple[str, list[list[str]]]] = []
    text_rows: list[list[str]] = []
    n = doc.page_count
    for i in range(n):
        _tick(progress, i, n)
        page = doc[i]
        try:
            tables = page.find_tables().tables
        except Exception:  # noqa: BLE001 - versões antigas ou páginas problemáticas
            tables = []
        for t, tab in enumerate(tables, 1):
            rows = [[("" if c is None else str(c).replace("\n", " ")) for c in row] for row in tab.extract()]
            if rows and any(any(c for c in r) for r in rows):
                sheets.append((f"Pág {i + 1} - Tabela {t}", rows))
        for block in page.get_text("blocks"):
            if block[6] == 0:
                for line in str(block[4]).splitlines():
                    if line.strip():
                        text_rows.append([line.strip()])
    tables_found = len(sheets)
    if not sheets:
        sheets.append(("Texto", text_rows or [[""]]))
    used: set[str] = set()
    names = [_sheet_name(nm, used) for nm, _ in sheets]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{k}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for k in range(1, len(sheets) + 1))
        z.writestr("[Content_Types].xml", _XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   f'{overrides}</Types>')
        z.writestr("_rels/.rels", _XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheet_tags = "".join(f'<sheet name="{_x(nm)}" sheetId="{k}" r:id="rId{k}"/>' for k, nm in enumerate(names, 1))
        z.writestr("xl/workbook.xml", _XML + f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="{_REL}">'
                   f'<sheets>{sheet_tags}</sheets></workbook>')
        rels = "".join(f'<Relationship Id="rId{k}" Type="{_REL}/worksheet" Target="worksheets/sheet{k}.xml"/>'
                       for k in range(1, len(sheets) + 1))
        z.writestr("xl/_rels/workbook.xml.rels", _XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for k, (_nm, rows) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{k}.xml", _sheet_xml(rows))
    _tick(progress, n, n)
    return {"sheets": len(sheets), "tables": tables_found}


# ---- PowerPoint --------------------------------------------------------------------------
def _page_png(page: "fitz.Page", dpi: int, max_side: int = 2400) -> tuple[bytes, int, int]:
    scale = dpi / 72
    long_side = max(page.rect.width, page.rect.height) * scale
    if long_side > max_side:
        scale *= max_side / long_side
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


def export_pptx(doc: "fitz.Document", path: str, progress: Progress = None, dpi: int = 150) -> dict:
    """Um slide por página, com a página inteira como imagem (o texto não fica editável)."""
    import _pptx_base
    n = doc.page_count
    r0 = doc[0].rect
    emu = 12700
    sw = min(max(int(r0.width * emu), 914400), 51206400)
    sh = min(max(int(r0.height * emu), 914400), 51206400)
    base = zipfile.ZipFile(io.BytesIO(_pptx_base.data()))
    skip = {"[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
    ctypes = base.read("[Content_Types].xml").decode("utf-8")
    pres = base.read("ppt/presentation.xml").decode("utf-8")
    prels = base.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
    slide_ids, rel_add, ct_add = [], [], ['<Default Extension="png" ContentType="image/png"/>']
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for item in base.namelist():
            if item not in skip:
                z.writestr(item, base.read(item))
        for i in range(n):
            _tick(progress, i, n)
            png, pw, ph = _page_png(doc[i], dpi)
            k = i + 1
            fit = min(sw / pw, sh / ph)
            cx, cy = int(pw * fit), int(ph * fit)
            ox, oy = (sw - cx) // 2, (sh - cy) // 2
            z.writestr(f"ppt/media/image{k}.png", png)
            z.writestr(f"ppt/slides/slide{k}.xml", (
                _XML + f'<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{_REL}" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree>'
                '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
                f'<p:pic><p:nvPicPr><p:cNvPr id="2" name="Página {k}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                f'<p:spPr><a:xfrm><a:off x="{ox}" y="{oy}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
                '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'))
            z.writestr(f"ppt/slides/_rels/slide{k}.xml.rels", (
                _XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="{_REL}/slideLayout" Target="../slideLayouts/slideLayout7.xml"/>'
                f'<Relationship Id="rId2" Type="{_REL}/image" Target="../media/image{k}.png"/></Relationships>'))
            slide_ids.append(f'<p:sldId id="{255 + k}" r:id="rId{100 + k}"/>')
            rel_add.append(f'<Relationship Id="rId{100 + k}" Type="{_REL}/slide" Target="slides/slide{k}.xml"/>')
            ct_add.append(f'<Override PartName="/ppt/slides/slide{k}.xml" '
                          'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
        ctypes = ctypes.replace("</Types>", "".join(ct_add) + "</Types>")
        prels = prels.replace("</Relationships>", "".join(rel_add) + "</Relationships>")
        pres = re.sub(r"<p:sldSz[^>]*/>", f'<p:sldSz cx="{sw}" cy="{sh}"/>', pres)
        pres = pres.replace("</p:sldMasterIdLst>", f'</p:sldMasterIdLst><p:sldIdLst>{"".join(slide_ids)}</p:sldIdLst>')
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("ppt/presentation.xml", pres)
        z.writestr("ppt/_rels/presentation.xml.rels", prels)
    _tick(progress, n, n)
    return {"slides": n}


# ---- Imagens ---------------------------------------------------------------------------
def export_images(doc: "fitz.Document", path: str, fmt: str = "png", dpi: int = 150,
                  progress: Progress = None) -> list[str]:
    """Uma imagem por página. Com várias páginas, acrescenta _001, _002… ao nome escolhido."""
    fmt = "jpg" if fmt.lower() in ("jpg", "jpeg") else "png"
    p = Path(path)
    stem = p.with_suffix("")
    n = doc.page_count
    out = []
    scale = dpi / 72
    for i in range(n):
        _tick(progress, i, n)
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        target = f"{stem}.{fmt}" if n == 1 else f"{stem}_{i + 1:03d}.{fmt}"
        pix.save(target)
        out.append(target)
    _tick(progress, n, n)
    return out
