@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Vertice PDF - gerar instalador
set "PY="
py -3.12 -c "import struct;assert struct.calcsize('P')==8" >nul 2>nul && set "PY=py -3.12"
if not defined PY (
  python -c "import sys,struct;assert sys.version_info[:2]>=(3,10) and struct.calcsize('P')==8" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [!] Python 3.12 64-bit nao encontrado. Rode: winget install -e --id Python.Python.3.12
  pause & exit /b 1
)
if not exist ".venv-build\Scripts\python.exe" ( %PY% -m venv .venv-build || goto :err )
call ".venv-build\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || goto :err
python build.py %* || goto :err
echo.
echo Pronto! O instalador esta na pasta "installer".
explorer installer
pause
exit /b 0
:err
echo.
echo [X] O build falhou. Veja as mensagens acima.
pause
exit /b 1
