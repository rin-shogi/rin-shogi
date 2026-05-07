@echo off
REM Rin floodgate runner (interactive)
REM Launch: double-click or run from a terminal
REM Stop: Ctrl-C (graceful: finishes the current game first)
REM
REM Prompts for handle name and trip (password) at startup.
REM Trip is passed to python via the FLOODGATE_PASSWORD env var
REM so it does not appear in the process listing (tasklist).
REM
REM NOTE: keep this .bat ASCII-only. cmd.exe parses .bat line-by-line
REM as bytes and chokes on multi-byte UTF-8 even with `chcp 65001`.
REM Japanese output from python is fine (PYTHONIOENCODING=utf-8 + chcp).

setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Rin floodgate runner
echo  config: configs/match/floodgate_v1.yaml
echo ============================================================
echo.

REM --- Handle name (default Rin-suisho5-v1) ---
set "HANDLE_DEFAULT=Rin-suisho5-v1"
set "HANDLE="
set /p HANDLE="Handle [%HANDLE_DEFAULT%]: "
if "%HANDLE%"=="" set "HANDLE=%HANDLE_DEFAULT%"

REM --- Trip (password) ---
REM cmd.exe set /p cannot mask input. Trip is sent in plaintext over
REM CSA anyway, so masking would be cosmetic. Echo as-is.
set "TRIP="
set /p TRIP="Trip      : "

if "%TRIP%"=="" (
    echo.
    echo [ERROR] Trip is empty. Aborting.
    pause
    endlocal
    exit /b 1
)

REM --- Pass to python: trip via env var, handle via CLI arg ---
set "FLOODGATE_PASSWORD=%TRIP%"

echo.
echo Handle: %HANDLE%
echo Trip  : (set, %TRIP:~0,2%***)
echo Ctrl-C to stop (current game will be played out).
echo ============================================================
echo.

python scripts\floodgate_client.py ^
    --config configs\match\floodgate_v1.yaml ^
    --username "%HANDLE%"

set RC=%errorlevel%
echo.
echo ============================================================
echo  Exited with code %RC%
echo ============================================================
pause
endlocal & exit /b %RC%
