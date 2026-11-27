@echo off
rem Opens the mirror window (the handheld plugged in, screen on).
cd /d "%~dp0"
start "" pythonw -I tools\mirror.py
