@echo off
REM Rin floodgate runner (Rin-suisho5-v1)
REM Launch: double-click or run from a terminal
REM Stop: Ctrl-C (graceful — finishes the current game first)

setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Rin floodgate runner (handle: Rin-suisho5-v1)
echo  config: configs/match/floodgate_v1.yaml
echo  Press Ctrl-C to stop (current game finishes first)
echo ============================================================
echo.

python scripts\floodgate_client.py --config configs\match\floodgate_v1.yaml

set RC=%errorlevel%
echo.
echo ============================================================
echo  Exited with code %RC%
echo ============================================================
pause
endlocal ^& exit /b %RC%
