# Rugby Prediction Pipeline (URC, Currie Cup)

Setup
- Python 3.11+ recommended
- Create venv and install deps

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Config
- Copy `.env.example` to `.env` and set `THESPORTSDB_API_KEY` (free key is `1`, limited)

Backfill
- Name-based (may fail on free key):
```bash
.venv\Scripts\python.exe -m scripts.backfill --db data.sqlite --max-seasons 1
```
- ID-based (preferred):
```bash
.venv\Scripts\python.exe -m scripts.backfill --db data.sqlite --league-ids <ID1> <ID2> --max-seasons 3
```

Notes
- API rate limit is 15 rpm; client has built-in limiter and retries
- Focus is Rugby Union tournaments like United Rugby Championship and Currie Cup
- Next steps: feature engineering (Elo, form), hybrid model training, predictions
