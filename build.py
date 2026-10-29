"""Pipeline de build do Vértice PDF: .exe (PyInstaller) -> autoteste -> instalador (Inno Setup).

Uso (no Windows, dentro do venv do projeto):
    python build.py                 # tudo
    python build.py --no-ocr        # instalador sem o Tesseract (menor)
    python build.py --no-vcredist   # sem o Microsoft Visual C++ Runtime
    python build.py --exe-only      # só gera dist\\VerticePDF (sem instalador)
Variável opcional: TESSERACT_SETUP_URL (outro link do instalador do Tesseract).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REDIST = ROOT / "redist"
IS_WIN = sys.platform == "win32"

VC_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
TESS_URL = os.environ.get(
    "TESSERACT_SETUP_URL",
    "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/"
    "tesseract-ocr-w64-setup-5.4.0.20240606.exe")
POR_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata"


def log(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def version() -> str:
    ns: dict = {}
    exec((ROOT / "version.py").read_text(encoding="utf-8-sig"), ns)
    return ns["__version__"]


def run(cmd: list, **kw) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=kw.pop("cwd", ROOT), **kw)


def download(url: str, dest: Path, min_bytes: int = 100_000) -> bool:
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        print(f"  (em cache) {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VerticePDF-build"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        if dest.stat().st_size < min_bytes:
            raise OSError("arquivo baixado é pequeno demais")
        print(f"  baixado {dest.name} ({dest.stat().st_size // 1024} KB)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  AVISO: não foi possível baixar {url}\n         {exc}")
        dest.unlink(missing_ok=True)
        return False


def version_info() -> str:
    ver = version()
    nums = (tuple(int(x) for x in ver.split(".")) + (0, 0, 0, 0))[:4]
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604b0', [
      StringStruct('CompanyName', 'V\\u00e9rtice PDF'),
      StringStruct('FileDescription', 'V\\u00e9rtice PDF - Editor de PDF'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'VerticePDF'),
      StringStruct('OriginalFilename', 'VerticePDF.exe'),
      StringStruct('ProductName', 'V\\u00e9rtice PDF'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ])
"""


def build_exe() -> Path:
    log("1/5  Ícone e metadados")
    run([sys.executable, "make_icon.py"])
    (ROOT / "version_info.txt").write_text(version_info(), encoding="utf-8")
    log("2/5  Gerando o programa (PyInstaller)")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "VerticePDF.spec"])
    exe = ROOT / "dist" / "VerticePDF" / ("VerticePDF.exe" if IS_WIN else "VerticePDF")
    if not exe.is_file():
        sys.exit("ERRO: o executável não foi gerado.")
    return exe


def selftest(exe: Path) -> None:
    log("3/5  Autoteste do programa empacotado")
    report = ROOT / "selftest_report.txt"
    report.unlink(missing_ok=True)
    env = dict(os.environ)
    if not IS_WIN:
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run([str(exe), "--selftest", str(report)], cwd=ROOT, env=env, timeout=300)
    text = report.read_text(encoding="utf-8") if report.exists() else "(sem relatório)"
    print(text)
    if proc.returncode != 0 or "TUDO OK" not in text:
        sys.exit("ERRO: o autoteste do programa empacotado falhou — o instalador NÃO foi gerado.")


def find_7z() -> str | None:
    for c in (shutil.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if c and Path(c).exists():
            return c
    return None


def prepare_tesseract() -> bool:
    """Extrai o Tesseract (instalador NSIS da UB Mannheim) para redist\\tesseract, sem instalar."""
    target = REDIST / "tesseract"
    if (target / "tesseract.exe").is_file() and (target / "tessdata" / "por.traineddata").is_file():
        print("  Tesseract já preparado (cache)")
        return True
    setup = REDIST / "tesseract-setup.exe"
    if not download(TESS_URL, setup, 20_000_000):
        return False
    seven = find_7z()
    if not seven and IS_WIN and shutil.which("winget"):
        print("  7-Zip não encontrado; tentando instalar via winget…")
        subprocess.run(["winget", "install", "-e", "--id", "7zip.7zip", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"])
        seven = find_7z()
    if not seven:
        print("  AVISO: 7-Zip não encontrado. Instale em https://www.7-zip.org e rode o build de novo.")
        return False
    raw = REDIST / "tesseract_raw"
    shutil.rmtree(raw, ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    run([seven, "x", "-y", f"-o{raw}", str(setup)])
    for junk in ("$PLUGINSDIR", "$R0", "[NSIS].nsi", "Uninstall.exe", "uninstall.exe"):
        p = raw / junk
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    if not (raw / "tesseract.exe").is_file():
        print("  AVISO: tesseract.exe não encontrado após extrair o instalador.")
        return False
    raw.rename(target)
    (target / "tessdata").mkdir(exist_ok=True)
    if not download(POR_URL, target / "tessdata" / "por.traineddata", 1_000_000):
        print("  AVISO: sem o idioma português; o OCR ficará só em inglês.")
    return True


def find_iscc() -> str | None:
    cands = [shutil.which("ISCC"),
             os.path.expandvars(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"),
             os.path.expandvars(r"%ProgramFiles%\Inno Setup 6\ISCC.exe"),
             os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")]
    return next((c for c in cands if c and Path(c).is_file()), None)


def build_installer(with_ocr: bool, with_vc: bool) -> Path:
    log("4/5  Preparando componentes do instalador")
    defines = [f"/DAppVersion={version()}"]
    if with_vc and download(VC_URL, REDIST / "vc_redist.x64.exe", 10_000_000):
        defines.append("/DWITH_VCREDIST")
    if with_ocr:
        if prepare_tesseract():
            defines.append("/DWITH_OCR")
        else:
            print("  >> Instalador será gerado SEM o componente de OCR.")
    log("5/5  Compilando o instalador (Inno Setup)")
    iscc = find_iscc()
    if not iscc and IS_WIN and shutil.which("winget"):
        print("  Inno Setup não encontrado; tentando instalar via winget…")
        subprocess.run(["winget", "install", "-e", "--id", "JRSoftware.InnoSetup", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"])
        iscc = find_iscc()
    if not iscc:
        sys.exit("ERRO: Inno Setup 6 não encontrado. Instale em https://jrsoftware.org/isdl.php")
    run([iscc, *defines, "installer.iss"])
    out = ROOT / "installer" / f"VerticePDF-Setup-{version()}.exe"
    if not out.is_file():
        sys.exit("ERRO: o instalador não foi gerado.")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (out.parent / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n")
    print(f"\n✔ Instalador pronto: {out}  ({out.stat().st_size // (1024 * 1024)} MB)\n  SHA-256: {digest}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--no-vcredist", action="store_true")
    ap.add_argument("--exe-only", action="store_true")
    ap.add_argument("--skip-selftest", action="store_true")
    args = ap.parse_args()
    exe = build_exe()
    if not args.skip_selftest:
        selftest(exe)
    if args.exe_only:
        print(f"\n✔ Programa pronto: {exe}")
        return
    if not IS_WIN:
        sys.exit("O instalador (Inno Setup) só pode ser gerado no Windows.")
    build_installer(not args.no_ocr, not args.no_vcredist)


if __name__ == "__main__":
    main()
