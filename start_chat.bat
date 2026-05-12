@echo off
set ANTHROPIC_API_KEY=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
cd /d "%~dp0"
start "" "http://localhost:5000"
.venv\Scripts\python.exe -m src.server
