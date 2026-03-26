@echo off
setlocal
cd /d "%~dp0"

echo Running GL Assistant Question Coverage Tests...
echo Output will be saved to robot\results\

robot ^
    --outputdir robot\results ^
    --output   questions_output.xml ^
    --log      questions_log.html ^
    --report   questions_report.html ^
    --name     "GL Question Coverage" ^
    robot\tests\questions_coverage.robot

echo.
echo Robot report : robot\results\questions_report.html
echo Plain summary: robot\results\questions_summary.txt
endlocal
