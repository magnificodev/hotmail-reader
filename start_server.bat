@echo off
cd /d d:\Workspace\beesmart\hotmail-reader\api
call .venv\Scripts\activate.bat
python -m uvicorn main:app --port 8000
