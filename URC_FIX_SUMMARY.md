# URC Upcoming Games Fix Summary

## Problem Identified
- **Issue**: No upcoming URC games showing in the application
- **Root Cause**: 
  1. TheSportsDB API `eventsnextleague.php` endpoint only returns 1 upcoming game for URC
  2. The `eventsseason.php` endpoint returns games but they all have scores (past games)
  3. Round scanning was optional and not enabled by default for URC
  4. Manual fixtures function existed but was unreachable code (after a return statement)

## Fixes Applied

### 1. Fixed Manual URC Fixtures Function
- **File**: `scripts/enhanced_auto_update.py`
- **Change**: Properly defined `get_manual_urc_fixtures()` function (was unreachable code)
- **Location**: Lines ~440-496

### 2. Integrated Manual Fixtures for URC
- **File**: `scripts/enhanced_auto_update.py`
- **Change**: Modified `detect_and_add_missing_games()` to use manual fixtures for URC when API fails
- **Location**: Lines ~387-405

### 3. Always Scan Rounds for URC
- **File**: `scripts/enhanced_auto_update.py`
- **Change**: Made round scanning automatic for URC (league ID 4446) to get more upcoming games
- **Location**: Line ~165
- **Impact**: URC will now scan all rounds (up to 18 rounds) to find upcoming fixtures

### 4. Enhanced Missing Games Detection
- **File**: `scripts/enhanced_auto_update.py`
- **Change**: Added logic to check manual fixtures even when some API games are found (to fill gaps)
- **Location**: Lines ~704-720

## Current API Status
Based on testing:
- ✅ `eventsnextleague.php` returns 1 upcoming game (Benetton vs Scarlets on 2026-01-30)
- ✅ `eventsseason.php` returns 15 games but all have scores (past games)
- ❌ `eventsleague.php` returns 404

## Next Steps

### 1. Run the Update Script
```bash
python scripts/enhanced_auto_update.py --scan-rounds
```

Or since URC now always scans rounds:
```bash
python scripts/enhanced_auto_update.py
```

### 2. Sync to Firestore
After updating the database:
```bash
python scripts/sync_to_firestore.py
```

### 3. Verify Games Are Added
Check the database:
```bash
python check_urc_games.py
```

### 4. Add Manual Fixtures (Optional)
If the API still doesn't return enough upcoming games, you can add them manually in `get_manual_urc_fixtures()` function:
- Update the `manual_fixtures` list with real upcoming URC fixtures
- Format: `{"date": "YYYY-MM-DD", "home": "Team Name", "away": "Team Name"}`

## Expected Results
After running the update script:
- URC should have upcoming games from round scanning
- Games should be in the database
- Games should sync to Firestore
- Games should appear in the frontend

## Testing
The test script `test_urc_api.py` can be used to verify API responses:
```bash
python test_urc_api.py
```
