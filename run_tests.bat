@echo off
setlocal
cd /d "%~dp0"

:: ── Activate virtualenv ───────────────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: .venv not found. Using system Python.
)

:: ── Choose which suite(s) to run ─────────────────────────────────────────────
:: Usage:
::   run_tests.bat            -> runs both suites
::   run_tests.bat assistant  -> runs assistant.robot only
::   run_tests.bat coverage   -> runs questions_coverage.robot only

set SUITE=%~1
if "%SUITE%"=="" set SUITE=all

set RESULTS=robot\results
if not exist "%RESULTS%" mkdir "%RESULTS%"

echo.
echo ============================================================
echo  GL Assistant Integration Tests
echo ============================================================
echo.

if "%SUITE%"=="assistant" goto :run_assistant
if "%SUITE%"=="coverage" goto :run_coverage

:run_both
echo [1/2] Running assistant.robot ...
python -m robot ^
    --outputdir %RESULTS% ^
    --output   assistant_output.xml ^
    --log      assistant_log.html ^
    --report   assistant_report.html ^
    --name     "GL Assistant Integration" ^
    robot\tests\assistant.robot
set RC_ASSISTANT=%ERRORLEVEL%

echo.
echo [2/2] Running questions_coverage.robot ...
python -m robot ^
    --outputdir %RESULTS% ^
    --output   coverage_output.xml ^
    --log      coverage_log.html ^
    --report   coverage_report.html ^
    --name     "GL Question Coverage" ^
    robot\tests\questions_coverage.robot
set RC_COVERAGE=%ERRORLEVEL%

echo.
echo ============================================================
echo  Results
echo ============================================================
echo  assistant.robot  : %RESULTS%\assistant_report.html   (exit %RC_ASSISTANT%)
echo  coverage.robot   : %RESULTS%\coverage_report.html    (exit %RC_COVERAGE%)
echo  Plain summary    : %RESULTS%\questions_summary.txt
echo ============================================================
goto :end

:run_assistant
echo Running assistant.robot ...
python -m robot ^
    --outputdir %RESULTS% ^
    --output   assistant_output.xml ^
    --log      assistant_log.html ^
    --report   assistant_report.html ^
    --name     "GL Assistant Integration" ^
    robot\tests\assistant.robot
set RC_ASSISTANT=%ERRORLEVEL%
echo  Report: %RESULTS%\assistant_report.html   (exit %RC_ASSISTANT%)
goto :end

:run_coverage
echo Running questions_coverage.robot ...
python -m robot ^
    --outputdir %RESULTS% ^
    --output   coverage_output.xml ^
    --log      coverage_log.html ^
    --report   coverage_report.html ^
    --name     "GL Question Coverage" ^
    robot\tests\questions_coverage.robot
set RC_COVERAGE=%ERRORLEVEL%
echo  Report  : %RESULTS%\coverage_report.html   (exit %RC_COVERAGE%)
echo  Summary : %RESULTS%\questions_summary.txt
goto :end

:end
endlocal
