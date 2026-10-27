"""Recuperação automática: cópias periódicas de documentos com alterações não salvas.

Sem dependência de Qt, para ser testável. Cada documento aberto tem um id; enquanto houver
alterações, `write` mantém `<id>.pdf` + `<id>.json` na pasta de recuperação. Salvar, descartar
ou fechar normalmente chama `discard`. Se o programa encerrar de forma inesperada, os arquivos
ficam e são oferecidos na próxima abertura.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

MAX_AGE_DAYS = 30


def data_root() -> Path:
    """Pasta de dados do app: %APPDATA%\\VerticePDF (Windows) — logs e recuperação ficam juntos."""
    base = os.environ.get("VERTICE_DATA")
    if base:
        root = Path(base)
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "VerticePDF"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "VerticePDF"
    root.mkdir(parents=True, exist_ok=True)
    return root


def recovery_dir() -> Path:
    d = data_root() / "recovery"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(doc_id: str, data: bytes, *, title: str, original: str | None, encrypted: bool) -> None:
    d = recovery_dir()
    tmp = d / f"{doc_id}.pdf.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, d / f"{doc_id}.pdf")  # troca atômica: nunca fica um arquivo pela metade
    (d / f"{doc_id}.json").write_text(
        json.dumps({"title": title, "original": original, "encrypted": encrypted, "time": time.time()}),
        encoding="utf-8")


def discard(doc_id: str) -> None:
    d = recovery_dir()
    for ext in (".pdf", ".json", ".pdf.tmp"):
        try:
            (d / f"{doc_id}{ext}").unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def pending() -> list[dict]:
    """Documentos recuperáveis (mais recentes primeiro). Remove restos antigos ou corrompidos."""
    out, now = [], time.time()
    d = recovery_dir()
    for meta in d.glob("*.json"):
        pdf = meta.with_suffix(".pdf")
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            if not pdf.is_file() or pdf.stat().st_size < 100 or now - info["time"] > MAX_AGE_DAYS * 86400:
                raise ValueError
        except (OSError, ValueError, KeyError):
            discard(meta.stem)
            continue
        out.append({"id": meta.stem, "pdf": str(pdf), **info})
    for orphan in d.glob("*.pdf.tmp"):
        orphan.unlink(missing_ok=True)
    return sorted(out, key=lambda x: x["time"], reverse=True)
