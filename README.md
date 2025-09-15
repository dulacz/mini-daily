# Local Daily Check-in (FastAPI)

A tiny web app (3 fixed daily goals) for personal use on your home LAN (WiFi). No auth, no cloud, single SQLite file. Access from phone or computer browser pointing to the same machine.

## Quick Start
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Then run `ipconfig` to find your IPv4 address and open `http://<IP>:8000/` on your phone.

## Modify Daily Tasks
Edit the `TASKS` list in `app/core/config.py`, save, then restart the server.

## Data Storage
SQLite file: `data/checkins.db` (copy it to back up). If deleted, it will be recreated (history lost).

## Run Tests
```powershell
pytest -q
```

## Optional Future Ideas
- Streak (consecutive days) statistics
- CSV export
- Web UI to customize tasks
- Charts / analytics

