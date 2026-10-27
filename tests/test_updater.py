import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import updater  # noqa: E402


@pytest.fixture(autouse=True)
def allow_files(monkeypatch, tmp_path):
    monkeypatch.setenv("VERTICE_ALLOW_FILE_UPDATES", "1")
    monkeypatch.setenv("VERTICE_DATA", str(tmp_path / "data"))


def test_version_compare():
    assert updater.is_newer("1.8.0", "1.7.1") and updater.is_newer("v2.0", "1.9.9")
    assert not updater.is_newer("1.7.1", "1.7.1") and not updater.is_newer("1.7", "1.7.0")
    assert updater.is_newer("1.7.10", "1.7.9")


def test_manifest_download_and_hash(tmp_path):
    exe = tmp_path / "VerticePDF-Setup-1.8.0.exe"
    exe.write_bytes(b"MZ" + os.urandom(5000))
    manifest = tmp_path / "latest.json"
    manifest.write_text(json.dumps({"version": "1.8.0", "url": exe.as_uri(),
                                    "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "notes": "novidades"}))
    info = updater.fetch_latest(manifest.as_uri())
    assert info["version"] == "1.8.0" and info["notes"] == "novidades"
    seen = []
    path = updater.download(info, lambda a, b: seen.append((a, b)), str(tmp_path / "dl"))
    assert Path(path).read_bytes() == exe.read_bytes() and seen
    info["sha256"] = "0" * 64                       # adulterado: precisa ser recusado e apagado
    with pytest.raises(updater.UpdateError):
        updater.download(info, None, str(tmp_path / "dl2"))
    assert not list((tmp_path / "dl2").glob("*"))


def test_github_release_format(monkeypatch):
    release = {"tag_name": "v1.9.0", "body": "notas", "assets": [
        {"name": "VerticePDF-Setup-1.9.0.exe", "browser_download_url": "https://x/VerticePDF-Setup-1.9.0.exe",
         "digest": "sha256:ABCDEF"},
        {"name": "outro.zip", "browser_download_url": "https://x/outro.zip"}]}
    monkeypatch.setattr(updater, "_get", lambda url: json.dumps(release).encode())
    info = updater.fetch_latest("https://api.github.com/repos/a/b/releases/latest")
    assert info["version"] == "1.9.0" and info["sha256"] == "abcdef" and info["name"].endswith(".exe")
    release["assets"][0].pop("digest")
    release["assets"].append({"name": "VerticePDF-Setup-1.9.0.exe.sha256", "browser_download_url": "https://x/s"})
    monkeypatch.setattr(updater, "_get", lambda url: b"1234  file.exe\n" if url == "https://x/s"
                        else json.dumps(release).encode())
    assert updater.fetch_latest("https://api.github.com/x")["sha256"] == "1234"


def test_security_rules(monkeypatch):
    monkeypatch.delenv("VERTICE_ALLOW_FILE_UPDATES")
    with pytest.raises(updater.UpdateError):
        updater.fetch_latest("http://exemplo.com/latest.json")      # só https
    with pytest.raises(updater.UpdateError):
        updater.download({"url": "https://x/a.exe", "sha256": "", "name": "a.exe"})   # sem hash = bloqueado
    with pytest.raises(updater.UpdateError):
        updater.fetch_latest("")


def test_installer_args_keep_install():
    args = updater.installer_args()
    assert "/SILENT" in args and "/CLOSEAPPLICATIONS" in args and "/UPDATED=1" in args
    assert not any("DIR" in a or "TASKS" in a for a in args)       # mantém pasta e opções já instaladas


def test_update_flow_in_app(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QMessageBox
    import main
    app = QApplication.instance() or QApplication([])
    exe = tmp_path / "VerticePDF-Setup-9.9.9.exe"
    exe.write_bytes(b"MZ" + os.urandom(2000))
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"version": "9.9.9", "url": exe.as_uri(), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest()}))
    launched = []
    monkeypatch.setattr(updater, "launch_installer", lambda p: launched.append(p))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setenv("VERTICE_UPDATE_URL", man.as_uri())
    quits = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quits.append(1)))
    win = main.MainWindow()
    assert win.update_url() == man.as_uri()
    win.install_update(str(exe))
    assert launched == [str(exe)] and quits
    win.deleteLater()
    app.processEvents()


def test_update_dialog_downloads(tmp_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from dialogs import UpdateDialog
    app = QApplication.instance() or QApplication([])
    exe = tmp_path / "VerticePDF-Setup-9.9.9.exe"
    exe.write_bytes(b"MZ" + os.urandom(3000))
    info = {"version": "9.9.9", "url": exe.as_uri(), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
            "notes": "x", "name": exe.name}
    dlg = UpdateDialog("1.7.1", "https://x/y", None, info)
    QTimer.singleShot(100, dlg.go.click)
    guard = QTimer()                          # trava de segurança do teste (cancelada ao terminar)
    guard.setSingleShot(True)
    guard.timeout.connect(dlg.reject)
    guard.start(5000)
    dlg.exec()
    guard.stop()
    assert dlg.installer_path and Path(dlg.installer_path).read_bytes() == exe.read_bytes()
    app.processEvents()
