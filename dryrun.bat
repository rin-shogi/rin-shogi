@echo off
REM Rin floodgate dry-run (mock CSA server + Fake USI Engine, 1-game completion)
REM No real network. Use this to sanity-check the code before a real run.
REM Expected tail: "ALL DRY-RUN TESTS PASSED"

setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Rin floodgate dry-run
echo ============================================================
echo.

echo [1/3] CSA-USI move conversion unit tests
python scripts\utils\test_csa_usi.py
if errorlevel 1 goto :fail

echo.
echo [2/3] CSA protocol unit tests
python scripts\utils\test_csa.py
if errorlevel 1 goto :fail

echo.
echo [3/3] floodgate_client end-to-end dry-run
python tests\test_floodgate_client_dryrun.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  ALL DRY-RUN TESTS PASSED
echo ============================================================
pause
endlocal & exit /b 0

:fail
echo.
echo ============================================================
echo  DRY-RUN FAILED (errorlevel=%errorlevel%)
echo ============================================================
pause
endlocal & exit /b 1
