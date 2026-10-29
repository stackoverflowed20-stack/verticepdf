# -*- mode: python ; coding: utf-8 -*-
# Spec do PyInstaller — gera dist/VerticePDF/ (pasta; mais compatível com antivírus que "onefile").
import os

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("pymupdf", "pyhanko", "pyhanko_certvalidator", "pytesseract", "oscrypto", "asn1crypto"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ["PIL.Image", "PySide6.QtPrintSupport", "exporters", "_pptx_base"]

# --- Enxugar o pacote: só Core/Gui/Widgets/PrintSupport são usados -------------------
UNUSED_QT = ["QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtWebSockets",
             "QtQml", "QtQuick", "QtQuickWidgets", "QtQuickControls2", "QtQuick3D", "Qt3DCore", "Qt3DRender",
             "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras", "QtMultimedia", "QtMultimediaWidgets",
             "QtCharts", "QtDataVisualization", "QtGraphs", "QtPdf", "QtPdfWidgets", "QtSql", "QtTest",
             "QtBluetooth", "QtNfc", "QtSensors", "QtSerialPort", "QtSvg", "QtSvgWidgets",
             "QtDesigner", "QtHelp", "QtOpenGL", "QtOpenGLWidgets", "QtPositioning", "QtLocation",
             "QtRemoteObjects", "QtScxml", "QtStateMachine", "QtTextToSpeech", "QtSpatialAudio",
             "QtHttpServer", "QtVirtualKeyboard", "QtUiTools", "QtXml", "QtConcurrent", "QtDBus"]
excludes = ["scipy", "pandas", "lxml", "sympy", "tkinter", "matplotlib", "IPython", "pytest", "numpy", "onnxruntime", "pymupdf4llm",
            "pymupdf.layout", "pymupdf_layout", "unittest", "pydoc", "doctest",
            "PySide6.scripts", "PySide6.support"] + ["PySide6." + m for m in UNUSED_QT]
_DROP = tuple(x.lower() for x in (
    "opengl32sw", "d3dcompiler", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6Svg", "Qt6OpenGL",
    "Qt6VirtualKeyboard", "Qt6WebEngine", "Qt6Multimedia", "Qt6Charts", "Qt6DataVisualization",
    "Qt6Designer", "Qt63D", "Qt6Sql", "Qt6Test",
    "pymupdf/layout", "mupdf-devel", "pymupdf4llm", "pymupdf_layout",
    "translations", "qtwebengine", "plugins/imageformats/qpdf", "plugins/imageformats/qsvg",
    "plugins/networkinformation", "plugins/tls", "plugins/multimedia", "plugins/sqldrivers",
    "plugins/qmltooling", "plugins/generic", "plugins/position", "plugins/sensors", "plugins/designer"))


def _keep(item):
    name = (item[0] + "|" + item[1]).replace("\\", "/").lower()
    return not any(d in name for d in _DROP)

a = Analysis(["main.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports,
             excludes=excludes, noarchive=False, optimize=2)
a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VerticePDF", console=False, upx=False,
          icon="assets/verticepdf.ico" if os.path.exists("assets/verticepdf.ico") else None,
          version="version_info.txt" if os.path.exists("version_info.txt") else None)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="VerticePDF")
