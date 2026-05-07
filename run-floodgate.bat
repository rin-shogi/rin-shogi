@echo off
REM Rin floodgate runner (Rin-suisho5-v1)
REM 起動: ダブルクリック or `run-floodgate.bat` をターミナルから
REM 停止: Ctrl-C(進行中の対局を完走後にグレースフル停止)

setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Rin floodgate runner (handle: Rin-suisho5-v1)
echo  config: configs/match/floodgate_v1.yaml
echo  Ctrl-C で停止(進行中の対局は完走)
echo ============================================================
echo.

python scripts\floodgate_client.py --config configs\match\floodgate_v1.yaml

set RC=%errorlevel%
echo.
echo ============================================================
echo  exited with code %RC%
echo ============================================================
pause
endlocal & exit /b %RC%
