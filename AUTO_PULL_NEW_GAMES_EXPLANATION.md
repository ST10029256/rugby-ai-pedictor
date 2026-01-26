# Automatic New Game Detection - How It Works

## ✅ Yes, the pipeline will always pull new games when available!

### How It Works

#### 1. **Daily Automatic Runs**
- **Schedule**: Runs every day at 22:00 UTC (00:00 SAST)
- **Frequency**: Once per day
- **Coverage**: All 9 leagues checked every run

#### 2. **Comprehensive Scanning**
Every day, the pipeline:
- ✅ Scans **all rounds** for all leagues (automatic)
- ✅ Checks `eventsnextleague.php` endpoints
- ✅ Checks `eventsseason.php` endpoints  
- ✅ Checks `eventsround.php` for all rounds (18 rounds for URC, 26 for Top 14, etc.)
- ✅ Looks up to **365 days ahead** (configured in pipeline)

#### 3. **Smart Duplicate Prevention**
- Checks database before inserting
- Only adds **new games** that don't exist
- Updates scores for completed games
- Prevents duplicates automatically

#### 4. **New Game Detection Flow**

```
Daily Pipeline Run (22:00 UTC)
    ↓
For each league:
    ↓
1. Fetch from API (all endpoints + all rounds)
    ↓
2. Compare with database
    ↓
3. Insert only NEW games (not in database)
    ↓
4. Update scores for completed games
    ↓
5. Sync to Firestore
```

### When New Games Are Added

#### Scenario 1: New Fixtures Announced
- **API adds new games** → Pipeline picks them up **within 24 hours**
- **Example**: URC announces Round 19 fixtures → Next pipeline run adds them

#### Scenario 2: Games Added to Rounds
- **API adds games to round endpoints** → Pipeline scans all rounds daily
- **Example**: Super Rugby adds games to Round 5 → Next run finds them

#### Scenario 3: Future Games Scheduled
- **Games scheduled 6 months ahead** → Pipeline catches them (365-day window)
- **Example**: World Cup 2027 games → Already in pipeline's date range

### Timeline

| Event | Detection Time |
|-------|---------------|
| New games added to API | **Within 24 hours** (next pipeline run) |
| Games added to round endpoints | **Within 24 hours** (all rounds scanned daily) |
| Games scheduled far in advance | **Within 24 hours** (365-day window) |

### What Gets Updated

✅ **New upcoming games** → Added automatically
✅ **Game scores** → Updated when games complete
✅ **All leagues** → Checked every run
✅ **All rounds** → Scanned every run

### Configuration

**Pipeline Settings** (`.github/workflows/check-for-updates.yml`):
```yaml
--days-ahead 365    # Looks 365 days into future
--days-back 14      # Also checks past 14 days for scores
```

**Automatic Features**:
- ✅ Round scanning: **Automatic for all leagues**
- ✅ All leagues: **Processed every run**
- ✅ Duplicate prevention: **Built-in**

### Example Timeline

**Day 1 (Monday)**: 
- Pipeline runs at 22:00 UTC
- Finds 50 upcoming URC games
- Adds them to database

**Day 2 (Tuesday)**:
- URC announces 10 more games for Round 12
- API adds them to `eventsround.php?id=4446&r=12`

**Day 3 (Wednesday)**:
- Pipeline runs at 22:00 UTC
- Scans Round 12 (automatic)
- Finds 10 new games
- Adds them to database
- **Result**: All 60 games now in database

### Limitations

⚠️ **24-hour delay**: New games added to API will be picked up on the next daily run (not instantly)

✅ **Solution**: Pipeline runs daily, so maximum delay is 24 hours

### Summary

| Feature | Status |
|---------|--------|
| Automatic new game detection | ✅ Yes |
| Daily scanning | ✅ Yes |
| All leagues covered | ✅ Yes |
| All rounds scanned | ✅ Yes |
| Duplicate prevention | ✅ Yes |
| Future games (365 days) | ✅ Yes |
| Maximum delay | 24 hours |

## Conclusion

**Yes, the pipeline will automatically pull new games when they become available!**

- Runs daily
- Scans comprehensively
- Detects new games automatically
- Maximum 24-hour delay
- No manual intervention needed

Your pipeline is fully automated and will keep your database up-to-date with all new games as they become available in the API.
