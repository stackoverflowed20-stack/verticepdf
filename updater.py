"""Atualização do aplicativo sem desinstalar: baixa o instalador novo, confere o SHA-256 e o executa por cima.

Sem dependência de Qt (testável). O instalador (Inno Setup) usa sempre o mesmo AppId, então ele atualiza a
pasta já instalada, mantém as opções escolhidas (tarefas, componentes, associação .pdf) e não toca nos dados do
usuário (configurações, recentes, recuperação, log), que ficam fora da pasta do programa.

Fonte das versões (version.UPDATE_URL, QSettings "update_url" ou variável VERTICE_UPDATE_URL):
  * API de "latest release" do GitHub:  https://api.github.com/repos/OWNER/REPO/releases/latest
  * ou um JSON simples:  {"version": "1.8.0", "url": "https://.../VerticePDF-Setup-1.8.0.exe",
                          "sha256": "…", "notes": "O que mudou"}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

TIMEOUT = 15


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    if not nums:
        raise UpdateError(f"Versão inválida: {text!r}")
    return tuple(int(n) for n in nums[:4])


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _allowed(url: str) -> bool:
    # só HTTPS; file:// apenas em testes (VERTICE_ALLOW_FILE_UPDATES=1)
    return url.lower().startswith("https://") or (
        os.environ.get("VERTICE_ALLOW_FILE_UPDATES") == "1" and url.lower().startswith("file://"))


def _get(url: str) -> bytes:
    if not _allowed(url):
        raise UpdateError("Endereço de atualização inseguro (use https).")
    req = urllib.request.Request(url, headers={"User-Agent": "VerticePDF-updater", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — https validado acima
            return r.read()
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(f"Não foi possível consultar as atualizações: {exc}") from exc


def fetch_latest(url: str) -> dict:
    """Devolve {'version','url','sha256','notes','name'} da versão mais recente publicada."""
    if not url:
        raise UpdateError("O endereço de atualização ainda não foi configurado.")
    try:
        data = json.loads(_get(url).decode("utf-8"))
    except ValueError as exc:
        raise UpdateError("Resposta de atualização inválida.") from exc
    if "tag_name" in data:                      # formato do GitHub Releases
        assets = data.get("assets") or []
        exe = next((a for a in assets if re.search(r"Setup.*\.exe$", a.get("name", ""), re.I)), None)
        if not exe:
            raise UpdateError("A versão publicada não tem instalador (.exe).")
        sha = ""
        digest = exe.get("digest") or ""
        if digest.startswith("sha256:"):
            sha = digest.split(":", 1)[1]
        else:
            side = next((a for a in assets if a.get("name") == exe["name"] + ".sha256"), None)
            if side:
                sha = _get(side["browser_download_url"]).decode("utf-8", "replace").split()[0]
        return {"version": data["tag_name"].lstrip("vV"), "url": exe["browser_download_url"], "sha256": sha.lower(),
                "notes": data.get("body") or "", "name": exe["name"]}
    for key in ("version", "url"):
        if key not in data:
            raise UpdateError(f"Resposta de atualização sem '{key}'.")
    return {"version": str(data["version"]).lstrip("vV"), "url": data["url"], "sha256": str(data.get("sha256", "")).lower(),
            "notes": data.get("notes", ""), "name": Path(data["url"]).name or "VerticePDF-Setup.exe"}


def download(info: dict, progress: Callable[[int, int], None] | None = None, dest_dir: str | None = None) -> str:
    """Baixa o instalador para uma pasta temporária e confere o SHA-256 (se informado)."""
    if not _allowed(info["url"]):
        raise UpdateError("Endereço de download inseguro (use https).")
    if not info.get("sha256") and os.environ.get("VERTICE_ALLOW_FILE_UPDATES") != "1":
        raise UpdateError("A versão publicada não traz o SHA-256; a atualização foi bloqueada por segurança.")
    folder = Path(dest_dir or tempfile.mkdtemp(prefix="verticepdf_update_"))
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / re.sub(r"[^\w.\-]", "_", info.get("name") or "VerticePDF-Setup.exe")
    h = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers={"User-Agent": "VerticePDF-updater"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(out, "wb") as f:  # noqa: S310
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(256 * 1024):
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except Exception as exc:  # noqa: BLE001
        out.unlink(missing_ok=True)
        raise UpdateError(f"Falha ao baixar a atualização: {exc}") from exc
    if info.get("sha256") and h.hexdigest() != info["sha256"].lower():
        out.unlink(missing_ok=True)
        raise UpdateError("O arquivo baixado não confere com o SHA-256 publicado (download corrompido ou adulterado).")
    return str(out)


def installer_args() -> list[str]:
    """Atualização por cima da instalação existente: mostra só o progresso, fecha/reabre o app, não reinicia o PC."""
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/UPDATED=1"]


def launch_installer(path: str) -> None:
    """Inicia o instalador desacoplado deste processo (o app deve encerrar logo em seguida)."""
    if sys.platform.startswith("win"):
        flags = 0x00000008 | 0x00000200       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, *installer_args()], creationflags=flags, close_fds=True)  # noqa: S603
    else:
        subprocess.Popen([path, *installer_args()], start_new_session=True, close_fds=True)  # noqa: S603
