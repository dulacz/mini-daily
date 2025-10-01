@echo off
cd /d "C:\src\mini-daily"
git pull --rebase --autostash
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause