@echo off
rem Opens CalcSuite (the calculators plugged in and switched on).
cd /d "%~dp0"
start "" pythonw -I tools\mirror.py
