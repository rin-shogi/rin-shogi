@echo off
REM Rin floodgate runner (interactive)
REM Launch: double-click or run from a terminal
REM Stop: Ctrl-C (graceful — finishes the current game first)
REM
REM 起動時にハンドル名と trip(パスワード)を聞きます。
REM trip は環境変数 FLOODGATE_PASSWORD として python に渡されるため、
REM プロセス一覧(tasklist)には現れません。

setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Rin floodgate runner
echo  config: configs/match/floodgate_v1.yaml
echo ============================================================
echo.

REM --- ハンドル名のプロンプト ---
set "HANDLE_DEFAULT=Rin-suisho5-v1"
set "HANDLE="
set /p HANDLE="ハンドル名 [%HANDLE_DEFAULT%]: "
if "%HANDLE%"=="" set "HANDLE=%HANDLE_DEFAULT%"

REM --- trip(パスワード)のプロンプト ---
REM 注: cmd.exe の set /p は入力をそのままエコーします(伏字にできません)。
REM    floodgate の trip はサーバへの送信時点で平文(LOGIN コマンドが平文)
REM    なので、ここで隠しても本質的なセキュリティ向上にはなりません。
set "TRIP="
set /p TRIP="trip       : "

if "%TRIP%"=="" (
    echo.
    echo [ERROR] trip が空です。終了します。
    pause
    endlocal
    exit /b 1
)

REM --- 環境変数として python に渡す(.env を上書き) ---
set "FLOODGATE_PASSWORD=%TRIP%"

echo.
echo ハンドル: %HANDLE%
echo trip    : (set, %TRIP:~0,2%***)
echo Ctrl-C で停止(進行中の対局は完走)
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
endlocal ^& exit /b %RC%
