@echo off
schtasks /End /TN "TendryRastreador" >nul 2>&1
echo Rastreador detenido.
timeout /t 3 >nul
