@echo off
echo ====================================================
echo Starting GitHub Push...
echo ====================================================

"C:\Program Files\Git\cmd\git.exe" remote add origin https://github.com/satyamofficial1500-droid/seo-auditor-saas.git
"C:\Program Files\Git\cmd\git.exe" branch -M main
"C:\Program Files\Git\cmd\git.exe" push -u origin main

echo.
echo ====================================================
echo If there were no errors above, your code is uploaded!
echo Refresh your GitHub page to verify.
echo ====================================================
pause
