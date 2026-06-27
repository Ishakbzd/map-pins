@echo off
REM Build GATI Route Manager as a single .exe

REM Kill any running instance first
taskkill /f /im "GATI Route Manager.exe" 2>nul

REM Clean previous build artifacts
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

python -m PyInstaller --onefile --windowed --name "GATI Route Manager" --hidden-import PyQt6.QtWebEngineWidgets --hidden-import PyQt6.QtWebChannel --hidden-import folium --hidden-import geopy --hidden-import pdfplumber --collect-all folium main.py
echo.
echo Build complete. .exe is in the dist\ folder.
pause
