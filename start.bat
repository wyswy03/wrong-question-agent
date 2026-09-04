@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动错题本...
start "" "http://127.0.0.1:8765"
python server.py
if errorlevel 1 (
  echo.
  echo 启动失败：请先安装 Python 3，并勾选 Add python.exe to PATH。
  echo 下载：https://www.python.org/downloads/windows/
)
pause
