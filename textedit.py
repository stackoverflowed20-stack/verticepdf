"""Edição de texto por parágrafo, preservando (quando possível) a fonte original."""
from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from ops import _pt, _sample_bg

ALIGN = {"left": 0, "center": 1, "right": 2, "justify": 3}
_BASE14 = {
    "sans": {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"},
    "serif": {(0, 0): "tiro", (1, 0): "tibo", (0, 1): "tiit", (1, 1): "tibi"},
    "mono": {(0, 0): "cour", (1, 0): "cobo", (0, 1): "coit", (1, 1): "cobi"},
}
_FAMILY_LABEL = {"sans": "Helvetica", "serif": "Times", "mono": "Courier"}
_STYLE_WORDS = ("psmt", "mt", "ps", "bolditalic", "boldoblique", "semibold", "bold",
                "italic", "oblique", "regular", "book", "light", "black", "medium")


def norm_family(name: str) -> str:
    """'ABCDEF+Arial-BoldMT' -> 'arial' (sem prefixo de subconjunto nem estilo)."""
    n = re.sub(r"^[A-Z]{6}\+", "", name or "")
    n = re.sub(r"[^a-z0-9]", "", n.lower())
    changed = True
    while changed:
        changed = False
        for w in _STYLE_WORDS:
            if n.endswith(w) and len(n) > len(w):
                n, changed = n[: -len(w)], True
    return n


def _base14_family(key: str) -> str | None:
    if key.startswith(("helvetica", "arial")):
        return "sans"
    if key.startswith("times"):
        return "serif"
    if key.startswith("courier"):
        return "mono"
    return None


def _flag_family(flags: int) -> str:
    return "mono" if flags & 8 else "serif" if flags & 4 else "sans"


# --------------------------------------------------------------------------
# Fontes instaladas no sistema
# --------------------------------------------------------------------------
_INDEX: list[tuple[str, bool, bool, str]] | None = None


def _font_dirs() -> list[Path]:
    dirs: list[Path] = []
    win = os.environ.get("WINDIR")
    if win:
        dirs += [Path(win) / "Fonts", Path.home() / "AppData/Local/Microsoft/Windows/Fonts"]
    if sys.platform == "darwin":
        dirs += [Path("/Library/Fonts"), Path("/System/Library/Fonts"), Path.home() / "Library/Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    return [d for d in dirs if d.is_dir()]


def font_index() -> list[tuple[str, bool, bool, str]]:
    """[(família_normalizada, negrito, itálico, caminho)] — montado uma vez."""
    global _INDEX
    if _INDEX is None:
        idx = []
        for d in _font_dirs():
            for p in d.rglob("*"):
                if p.suffix.lower() in (".ttf", ".otf"):
                    try:
                        f = fitz.Font(fontfile=str(p))
                        idx.append((norm_family(f.name), bool(f.is_bold), bool(f.is_italic), str(p)))
                    except Exception:  # noqa: BLE001
                        continue
        _INDEX = idx
    return _INDEX


def find_system_font(key: str, bold: bool, italic: bool) -> str | None:
    same = [e for e in font_index() if e[0] == key]
    for b, i in ((bold, italic), (bold, False), (False, False)):
        for _k, eb, ei, path in same:
            if eb == b and ei == i:
                return path
    return same[0][3] if same else None


# --------------------------------------------------------------------------
# Plano de fonte
# --------------------------------------------------------------------------
@dataclass
class FontPlan:
    name: str
    buffer: bytes | None = None
    file: str | None = None
    note: str = ""


def _covers(font: "fitz.Font", text: str) -> bool:
    return all(font.has_glyph(ord(c)) for c in set(text) if not c.isspace())


def plan_font(doc, page, orig_font: str, orig_flags: int, text: str, family: str,
              bold: bool, italic: bool) -> FontPlan:
    key = norm_family(orig_font)
    same_style = bool(orig_flags & 16) == bold and bool(orig_flags & 2) == italic

    if family in _BASE14:
        return FontPlan(_BASE14[family][(int(bold), int(italic))])
    if family != "original":  # família instalada no sistema (chave normalizada)
        path = find_system_font(family, bold, italic)
        if path and _covers(fitz.Font(fontfile=path), text):
            return FontPlan("S" + hashlib.md5(path.encode()).hexdigest()[:8], file=path)
        fam = _flag_family(orig_flags)
        return FontPlan(_BASE14[fam][(int(bold), int(italic))],
                        note=f"Fonte “{family.title()}” indisponível ou sem os caracteres; usada {_FAMILY_LABEL[fam]}.")

    fam14 = _base14_family(key)
    if fam14:  # fontes padrão do PDF: o equivalente base-14 é fiel
        return FontPlan(_BASE14[fam14][(int(bold), int(italic))])

    if same_style:  # 1) a própria fonte embutida, se tiver todos os glifos
        for xref, _ext, _typ, basefont, *_ in page.get_fonts(full=True):
            if norm_family(basefont) == key:
                try:
                    buf = doc.extract_font(xref)[3]
                    if buf and _covers(fitz.Font(fontbuffer=buf), text):
                        return FontPlan(f"E{xref}", buffer=buf)
                except Exception:  # noqa: BLE001
                    pass
                break

    path = find_system_font(key, bold, italic)  # 2) mesma família instalada
    if path and _covers(fitz.Font(fontfile=path), text):
        return FontPlan("S" + hashlib.md5(path.encode()).hexdigest()[:8], file=path)

    fam = _flag_family(orig_flags)  # 3) equivalente padrão
    return FontPlan(_BASE14[fam][(int(bold), int(italic))],
                    note=f"Fonte original “{re.sub(r'^[A-Z]{6}[+]', '', orig_font)}” indisponível; "
                         f"usada {_FAMILY_LABEL[fam]}.")


def _install(page, plan: FontPlan) -> str:
    if plan.buffer is not None:
        page.insert_font(fontname=plan.name, fontbuffer=plan.buffer)
    elif plan.file:
        page.insert_font(fontname=plan.name, fontfile=plan.file)
    return plan.name


# --------------------------------------------------------------------------
# Parágrafos
# --------------------------------------------------------------------------
def _guess_align(lines: list[dict]) -> str:
    if len(lines) < 2:
        return "left"
    x0 = [l["bbox"][0] for l in lines]
    x1 = [l["bbox"][2] for l in lines]
    mid = [(a + b) / 2 for a, b in zip(x0, x1)]
    tol = 2.5
    spread = lambda v: max(v) - min(v)  # noqa: E731
    if spread(x0) <= tol and spread(x1[:-1]) <= tol:
        return "justify" if spread(x1[:-1]) <= tol and len(lines) > 2 else "left"
    if spread(x1) <= tol:
        return "right"
    if spread(mid) <= tol:
        return "center"
    return "left"


def block_at(page, pt) -> dict | None:
    """Parágrafo (bloco de texto) sob o ponto, em coordenadas exibidas."""
    p = _pt(page, pt)
    best, best_area = None, 1e18
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        r = fitz.Rect(block["bbox"])
        if not r.contains(p) or r.get_area() >= best_area:
            continue
        lines = [l for l in block["lines"] if any(s["text"].strip() for s in l["spans"])]
        if not lines:
            continue
        spans = [s for l in lines for s in l["spans"] if s["text"].strip()]
        first = spans[0]
        size = first["size"]
        ratio = 1.2
        if len(lines) > 1:
            gap = (lines[-1]["bbox"][1] - lines[0]["bbox"][1]) / (len(lines) - 1)
            ratio = max(0.9, min(2.5, gap / size))
        text = " ".join("".join(s["text"] for s in l["spans"]).strip() for l in lines)
        best_area = r.get_area()
        best = {
            "bbox": tuple(block["bbox"]), "text": text, "size": size,
            "color": fitz.sRGB_to_pdf(first["color"]), "flags": first["flags"],
            "font": first["font"], "align": _guess_align(lines),
            "lineheight": ratio, "nlines": len(lines),
        }
    return best


def replace_block(page, block: dict, new_text: str, *, family: str = "original",
                  size: float | None = None, bold: bool | None = None,
                  italic: bool | None = None, color=None, align: str | None = None) -> str:
    """Substitui o parágrafo. Retorna um aviso (vazio se tudo correu bem).

    Levanta ValueError se o texto novo não couber; quem chama deve desfazer.
    """
    size = size or block["size"]
    bold = bool(block["flags"] & 16) if bold is None else bold
    italic = bool(block["flags"] & 2) if italic is None else italic
    color = color or block["color"]
    align = align or block["align"]
    doc = page.parent

    plan = plan_font(doc, page, block["font"], block["flags"], new_text, family, bold, italic)
    bbox = fitz.Rect(block["bbox"])
    fill = _sample_bg(page, bbox.transform(page.rotation_matrix))

    page.add_redact_annot(bbox, fill=fill)
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    except TypeError:  # PyMuPDF antigo
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    fontname = _install(page, plan)

    def attempt(sz: float, rect: "fitz.Rect") -> float:
        return page.insert_textbox(rect, new_text, fontsize=sz, fontname=fontname, color=color,
                                   align=ALIGN[align], lineheight=block["lineheight"],
                                   rotate=page.rotation)

    box = fitz.Rect(bbox.x0, bbox.y0, bbox.x1 + 2, bbox.y1 + 2)
    sz = size
    while sz >= size * 0.7:  # 1º: reduz a fonte até 30% para caber no espaço original
        if attempt(sz, box) >= 0:
            return plan.note + (f" Fonte reduzida para {sz:.1f} pt." if sz < size else "")
        sz -= 0.5
    tall = fitz.Rect(box.x0, box.y0, box.x1, max(box.y1, page.rect.y1 - 24))  # 2º: cresce para baixo
    if attempt(size, tall) >= 0:
        return (plan.note + " O parágrafo ficou maior que o original.").strip()
    raise ValueError("O novo texto não cabe na página nesse ponto.")


# ==========================================================================
# Edição por palavra: troca SÓ a palavra escolhida (como num processador de texto)
# ==========================================================================
def _is_core(chars: list[dict], i: int) -> bool:
    """Caractere que faz parte do "miolo" de uma palavra (letras, dígitos, hífen/apóstrofo internos)."""
    c = chars[i]["c"]
    if c.isalnum() or c == "_":
        return True
    if c in "-'’" and 0 < i < len(chars) - 1:
        return chars[i - 1]["c"].isalnum() and chars[i + 1]["c"].isalnum()
    if c in "/.,:@" and 0 < i < len(chars) - 1:   # datas, números (1.234,56), horas, e-mails
        a, b = chars[i - 1]["c"], chars[i + 1]["c"]
        return (a.isdigit() and b.isdigit()) or (c in "@." and a.isalnum() and b.isalnum())
    return False


def _flat_chars(line: dict) -> list[dict]:
    out = []
    for span in line["spans"]:
        for ch in span.get("chars", []):
            out.append({"c": ch["c"], "origin": ch["origin"], "bbox": ch["bbox"], "font": span["font"],
                        "size": span["size"], "color": span["color"], "flags": span["flags"]})
    return out


def _style(ch: dict) -> dict:
    return {"font": ch["font"], "size": ch["size"], "color": fitz.sRGB_to_pdf(ch["color"]), "flags": ch["flags"]}


def _build_word(page, block, chars: list[dict], a: int, b: int) -> dict:
    """Monta o dicionário de edição para chars[a..b] (inclusive) de uma linha."""
    # "cauda": o que vem depois, na mesma linha, em pedaços separados por espaço.
    # Um vão grande (coluna/tabulação) encerra a cauda: o que está além não se move.
    size_ref = chars[a]["size"]
    tail, cur, beyond = [], [], None
    prev_x1 = chars[b]["bbox"][2]
    for ch in chars[b + 1:]:
        if ch["c"].isspace():
            if cur:
                tail.append(cur)
                cur = []
            continue
        gap = ch["bbox"][0] - prev_x1
        if not cur and gap > 1.6 * size_ref:
            beyond = ch["bbox"][0]
            break
        cur.append(ch)
        prev_x1 = ch["bbox"][2]
    if cur and beyond is None:
        tail.append(cur)
    first = chars[a]
    y0 = min(c["bbox"][1] for c in chars if not c["c"].isspace())
    y1 = max(c["bbox"][3] for c in chars if not c["c"].isspace())
    x0, x1 = first["origin"][0], chars[b]["bbox"][2]
    tail_end = tail[-1][-1]["bbox"][2] if tail else x1
    limit = beyond if beyond is not None else page.rect.x1 - 6
    for ow in page.get_text("words"):   # outro texto (coluna ao lado) na mesma faixa vertical
        if ow[0] >= tail_end - 0.5 and ow[0] < limit and min(ow[3], y1) - max(ow[1], y0) > 0.5 * (y1 - y0) \
                and not (ow[0] <= tail_end + 0.5):
            limit = ow[0]
    return {
        "text": "".join(c["c"] for c in chars[a:b + 1]),
        "x0": x0, "x1": x1, "baseline": first["origin"][1], "y0": y0, "y1": y1,
        "rect": (x0, y0, x1, y1), "para": tuple(block["bbox"]), "limit": limit,
        **_style(first),
        "tail": [{"text": "".join(c["c"] for c in t), "x0": t[0]["origin"][0],
                  "x1": t[-1]["bbox"][2], **_style(t[0])} for t in tail],
    }


def word_at(page, pt) -> dict | None:
    """Palavra sob o ponto (coords. exibidas) com tudo que é preciso para trocá-la.

    Retorna None em páginas giradas, texto vertical ou quando o clique não cai numa palavra.
    """
    if page.rotation:
        return None
    p = fitz.Point(pt)
    for block in page.get_text("rawdict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            if abs(line["dir"][0] - 1) > 0.01:      # só texto horizontal
                continue
            if not (fitz.Rect(line["bbox"]) + (-1.5, -1.5, 1.5, 1.5)).contains(p):
                continue
            chars = _flat_chars(line)
            idx = next((i for i, ch in enumerate(chars)
                        if ch["bbox"][0] - 0.5 <= p.x <= ch["bbox"][2] + 0.5 and _is_core(chars, i)), None)
            if idx is None:
                continue
            a = b = idx
            while a > 0 and _is_core(chars, a - 1):
                a -= 1
            while b < len(chars) - 1 and _is_core(chars, b + 1):
                b += 1
            return _build_word(page, block, chars, a, b)
    return None


def find_matches(page, query: str, case: bool = False) -> list[dict]:
    """Ocorrências de `query` dentro de uma linha (como dicionários de edição, na ordem da página)."""
    out: list[dict] = []
    if not query.strip() or page.rotation:
        return out
    rx = re.compile(re.escape(query), 0 if case else re.IGNORECASE)
    for block in page.get_text("rawdict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            if abs(line["dir"][0] - 1) > 0.01:
                continue
            chars = _flat_chars(line)
            text = "".join(c["c"] for c in chars)
            for m in rx.finditer(text):
                a, b = m.start(), m.end() - 1
                if not text[a:b + 1].strip() or chars[a]["c"].isspace() or chars[b]["c"].isspace():
                    continue
                out.append(_build_word(page, block, chars, a, b))
    return out


def replace_all(doc, query: str, repl: str, case: bool = False, pages: list[int] | None = None,
                progress=None) -> dict:
    """Localizar e substituir. Preserva fonte/tamanho/cor de cada ocorrência.

    Retorna {"count": n, "skipped": m, "pages": p, "notes": [...]}; ocorrências que não cabem
    (invadiriam outra coluna ou a margem) são puladas e contadas em "skipped".
    """
    res = {"count": 0, "skipped": 0, "pages": 0, "notes": []}
    todo = list(range(doc.page_count)) if pages is None else pages
    for n, pno in enumerate(todo):
        page = doc[pno]
        if progress:
            progress(n, len(todo))
        pointer = (-1e9, -1e9)      # ordem de leitura: o que já foi tratado nunca é reavaliado
        changed = False
        for _ in range(3000):
            def key(m):
                return (round(m["baseline"] / 2), m["x0"])
            ms = [m for m in find_matches(page, query, case) if key(m) > pointer]
            if not ms:
                break
            m = min(ms, key=key)
            try:
                note, new_w = _replace_word(page, m, repl, allow_empty=True)
            except ValueError:
                res["skipped"] += 1
                pointer = (key(m)[0], m["x1"])
                continue
            res["count"] += 1
            changed = True
            if note and note not in res["notes"]:
                res["notes"].append(note)
            pointer = (key(m)[0], m["x0"] + max(new_w, 0.5))
        res["pages"] += 1 if changed else 0
    return res


def _font_object(plan: FontPlan) -> "fitz.Font":
    if plan.buffer is not None:
        return fitz.Font(fontbuffer=plan.buffer)
    if plan.file:
        return fitz.Font(fontfile=plan.file)
    return fitz.Font(plan.name)


def replace_word(page, w: dict, new_text: str, *, size: float | None = None, bold: bool | None = None,
                 italic: bool | None = None, color=None, family: str = "original") -> str:
    """Troca somente a palavra `w` (de word_at). O resto da linha acompanha a nova largura.

    Retorna um aviso (vazio se tudo correu bem); levanta ValueError se não for possível.
    """
    return _replace_word(page, w, new_text, size=size, bold=bold, italic=italic, color=color, family=family)[0]


def _replace_word(page, w: dict, new_text: str, *, size=None, bold=None, italic=None, color=None,
                  family: str = "original", allow_empty: bool = False) -> tuple[str, float]:
    if page.rotation:
        raise ValueError("Editar palavras em páginas giradas ainda não é suportado.")
    new_text = new_text.strip()
    if not new_text and not allow_empty:
        raise ValueError("O texto novo está vazio.")
    doc = page.parent
    size = size or w["size"]
    bold = bool(w["flags"] & 16) if bold is None else bold
    italic = bool(w["flags"] & 2) if italic is None else italic
    color = color or w["color"]
    notes = []

    plan = plan_font(doc, page, w["font"], w["flags"], new_text, family, bold, italic)
    if plan.note:
        notes.append(plan.note)
    new_w = _font_object(plan).text_length(new_text, fontsize=size) if new_text else 0.0
    delta = new_w - (w["x1"] - w["x0"])
    tail = w["tail"]
    end_x = (tail[-1]["x1"] if tail else w["x1"]) + delta
    if end_x > page.rect.x1 - 6:
        raise ValueError("A palavra nova é grande demais: a linha passaria da margem da página.")
    if end_x > w.get("limit", 1e9) - 1.0:
        raise ValueError("A palavra nova é grande demais: ela invadiria o texto ao lado (outra coluna ou célula).")
    if end_x > w["para"][2] + 2:
        notes.append("A linha ficou mais larga que o parágrafo original.")

    h = w["y1"] - w["y0"]
    right = (tail[-1]["x1"] if tail else w["x1"]) + 0.6
    rect = fitz.Rect(w["x0"] + 0.1, w["y0"] + h * 0.12, right, w["y1"] - h * 0.12)
    fill = _sample_bg(page, rect)
    page.add_redact_annot(rect, fill=fill)
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    except TypeError:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    name = _install(page, plan)
    if new_text:
        page.insert_text((w["x0"], w["baseline"]), new_text, fontsize=size, fontname=name, color=color)
    for tok in tail:  # o restante da linha, deslocado pela diferença de largura
        tplan = plan_font(doc, page, tok["font"], tok["flags"], tok["text"], "original",
                          bool(tok["flags"] & 16), bool(tok["flags"] & 2))
        if tplan.note:
            notes.append("Parte do texto da linha usou uma fonte equivalente.")
        page.insert_text((tok["x0"] + delta, w["baseline"]), tok["text"], fontsize=tok["size"],
                         fontname=_install(page, tplan), color=tok["color"])
    return " ".join(dict.fromkeys(notes)), new_w


def system_families() -> list[str]:
    """Famílias instaladas (chaves normalizadas), para o seletor de fonte."""
    return sorted({e[0] for e in font_index() if e[0]})
