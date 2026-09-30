@echo off
rem Doble clic para arrancar la app. Salta la politica de ejecucion solo para este script.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0arrancar.ps1"
if errorlevel 1 pause
