@echo off
rem DocuEngine OCR worker — keep this window open while using the app.
rem Consumes BOTH queues (cpu + ocr_gpu); without -Q the ocr_page tasks never run.
rem If the worker crashes it restarts automatically after 5 seconds.
title DocuEngine OCR Worker
cd /d "%~dp0backend"
set PYTHONIOENCODING=utf8
:loop
.venv\Scripts\celery.exe -A app.tasks.celery_app worker --pool=solo -l info -Q cpu,ocr_gpu
echo.
echo Worker stopped (exit %errorlevel%) - restarting in 5 seconds... Press Ctrl+C to quit.
timeout /t 5 /nobreak >nul
goto loop
