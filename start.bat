@echo off
rem ASCII shell: delegate to start.ps1 (handles Chinese paths).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
