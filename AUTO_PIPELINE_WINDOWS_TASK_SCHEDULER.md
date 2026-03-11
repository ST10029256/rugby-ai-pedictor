# Automatic Daily Pipeline (Windows Task Scheduler)

This repo’s “pipeline” (fetch fixtures → update `data.sqlite` → sync to Firestore) is **not automatic by default**.  
To run it automatically on Windows, use Task Scheduler to execute `scripts/run_pipeline.ps1`.

## Prerequisites

- Python installed and available as `python`
- You can run these successfully in PowerShell from the repo root:
  - `python scripts/enhanced_auto_update.py --db data.sqlite --days-ahead 365`
    - Note: Round scanning is now automatic for all leagues (no `--scan-rounds` flag needed)
  - `python scripts/sync_to_firestore.py`
- Your Firestore auth is already working (same machine/user you tested with)

## Create the Scheduled Task

1. Open **Task Scheduler**
2. Click **Create Task** (not “Basic Task”)
3. **General**
   - Name: `Rugby AI - Daily Pipeline`
   - Select **Run whether user is logged on or not** (optional)
   - Check **Run with highest privileges** (recommended)
4. **Triggers**
   - New… → Daily → pick a time (e.g. 2:00 AM)
5. **Actions**
   - New… → Start a program
   - Program/script: `powershell.exe`
   - Add arguments:
     - `-ExecutionPolicy Bypass -File "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\scripts\run_pipeline.ps1"`
   - Start in:
     - `C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main`
6. Click **OK**

## Customize (optional)

To change how far ahead it fetches fixtures, edit the task "Add arguments" like this:

- Example (1 year ahead):
  - `-ExecutionPolicy Bypass -File "...\\scripts\\run_pipeline.ps1" -DaysAhead 365`
  - Note: Round scanning is automatic for all leagues - no `-ScanRounds` flag needed

## Logs

- Firestore sync log: `firestore_sync.log` (created by `scripts/sync_to_firestore.py`)


