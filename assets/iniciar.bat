@echo off
rem Abre el lanzador grafico sin dejar una consola abierta
cd /d "%~dp0"
start "" pythonw "%~dp0servidor.py"
