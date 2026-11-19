@echo off
setlocal EnableDelayedExpansion
title Willow - start
echo.
echo  Willow - start
echo  ==============
echo.

if not exist willow-config.txt (
  echo Willow is not installed yet. Double-click install.bat first.
  echo.
  echo Or use the free hosted API trial (3 hours free):
  echo   https://api.adventists.ai/console
  goto :end
)

set "BUILD=4B-W4"
set "ROUTE=repo"
set "ENGINE_DIR=sophon-realtime/tag"
set "PORT=8000"
for /f "tokens=1,2 delims==" %%a in (willow-config.txt) do (
  if "%%a"=="BUILD" set "BUILD=%%b"
  if "%%a"=="ROUTE" set "ROUTE=%%b"
  if "%%a"=="ENGINE_DIR" set "ENGINE_DIR=%%b"
  if "%%a"=="PORT" set "PORT=%%b"
)

wsl -l -q 2>nul | findstr /I /C:"Ubuntu" >nul
if errorlevel 1 (
  echo WSL Ubuntu is not installed. Run install.bat first.
  goto :end
)
for /f "tokens=*" %%p in ('wsl wslpath -a "%~dp0"') do set "WSL_HERE=%%p"

echo Willow (!BUILD!) is starting...
echo.
echo Talk to Willow here:
echo   ws://localhost:!PORT!/v1/realtime
echo.
echo Open talk.html in this folder in your browser, press Connect, then talk.
echo (If you have not added a voice clip yet, set the Voice box to chelsie.)
echo.
echo First start can take 5-10 minutes (the engine builds its kernels once).
echo.

if "!ROUTE!"=="pip" (
  wsl -d Ubuntu bash -c "export PATH=$HOME/.local/bin:$PATH; sophon-realtime serve"
) else (
  wsl -d Ubuntu bash -c "cd !WSL_HERE!!ENGINE_DIR! && GPU=0 PORT=!PORT! bash start.sh"
)

echo.
echo Willow is running. Open talk.html now.
echo To stop Willow later, run this in WSL Ubuntu:
echo   bash !WSL_HERE!!ENGINE_DIR!/stop.sh
goto :end

:end
echo.
pause
