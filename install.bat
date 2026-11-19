@echo off
setlocal EnableDelayedExpansion
title Willow - install
echo.
echo  Willow - install
echo  ================
echo.

REM --- 1. Find the GPU and its memory ---
where nvidia-smi >nul 2>&1
if errorlevel 1 goto :nogpu
set "VRAM_MB="
for /f "tokens=*" %%a in ('nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2^>nul') do if not defined VRAM_MB set "VRAM_MB=%%a"
if not defined VRAM_MB goto :nogpu
echo Your GPU memory: %VRAM_MB% MB
if %VRAM_MB% GEQ 80000 goto :build32
if %VRAM_MB% GEQ 24000 goto :build4b
goto :hosted

:build32
echo.
echo Your GPU has %VRAM_MB% MB - that is a datacentre card, not a normal PC card.
echo The 32B Tag build fits on it, so Willow will install that.
echo If this is a rented or cloud GPU, you are good. A normal home PC will
echo never show this number - the 4B and hosted routes below are the usual ones.
set "BUILD=32B"
goto :wslcheck

:build4b
echo.
echo Your GPU has %VRAM_MB% MB - the 4B build fits.
echo Willow will install Tag-4B-W4 (about 21 GB of weights).
echo The full 32B build needs an 80 GB GPU and does NOT fit this PC.
echo If you want 32B later, rent one on RunPod or use the free hosted API trial.
set "BUILD=4B-W4"
goto :wslcheck

:hosted
echo.
echo No GPU with enough memory was found.
echo Willow will use the free hosted API trial instead (3 hours free).
echo Sign up at https://api.adventists.ai/console
echo Then open talk.html and set the address to the hosted API.
goto :end

:nogpu
echo.
echo No NVIDIA GPU was found on this PC.
echo Willow will use the free hosted API trial instead (3 hours free).
echo Sign up at https://api.adventists.ai/console
goto :end

:wslcheck
echo.
echo Checking for WSL Ubuntu (the Linux side Willow runs in)...
wsl -l -q 2>nul | findstr /I /C:"Ubuntu" >nul
if errorlevel 1 goto :nowsl
for /f "tokens=*" %%p in ('wsl wslpath -a "%~dp0"') do set "WSL_HERE=%%p"
echo Installing inside WSL Ubuntu. This downloads about 21 GB (4B) or 42 GB (32B).
echo Keep this window open - it takes a while.
wsl -d Ubuntu bash "!WSL_HERE!setup-willow.sh" !BUILD!
if errorlevel 1 (
  echo.
  echo Install stopped with an error. Read the lines above, then run install.bat again.
  goto :end
)
echo.
echo Done. Double-click start-willow.bat to talk to Willow.
goto :end

:nowsl
echo.
echo WSL Ubuntu is not installed on this PC.
echo To install it, open PowerShell as Administrator and run:
echo   wsl --install -d Ubuntu
echo Then restart the PC and double-click install.bat again.
echo.
echo Or use the free hosted API trial now (3 hours free):
echo   https://api.adventists.ai/console
goto :end

:end
echo.
pause
