# 🏉 Automated Rugby Game Updates Setup Guide

This guide explains how to set up automated pulling of upcoming rugby games from APIs to keep your prediction database up-to-date.

## 📋 Overview

The system includes several scripts to automatically pull upcoming games:

- **`simple_auto_update.py`** - Main script (recommended)
- **`auto_pull_upcoming.py`** - Comprehensive version with more features
- **`schedule_updates.py`** - Scheduler wrapper
- **GitHub Actions workflow** - For cloud-based automation

## 🚀 Quick Start

### 1. Test the Script (Dry Run)

```bash
# Test with dry run (no changes made)
python scripts/simple_auto_update.py --dry-run --verbose

# Test specific league
python scripts/simple_auto_update.py --dry-run --leagues 4574 --verbose
```

### 2. Run for Real

```bash
# Update all supported leagues
python scripts/simple_auto_update.py --verbose

# Update specific leagues
python scripts/simple_auto_update.py --leagues 4986 4574 --verbose
```

## 🔑 API Keys Setup

### TheSportsDB (Free)
- **Key**: `123` (already configured)
- **Works for**: Rugby World Cup
- **Setup**: No additional setup needed

### API-Sports (Premium)
- **Get key from**: https://api-sports.io/
- **Works for**: Rugby Championship
- **Setup**: Set environment variable
  ```bash
  # Windows
  set APISPORTS_API_KEY=your_key_here
  
  # Linux/Mac
  export APISPORTS_API_KEY=your_key_here
  ```

## 📅 Automated Scheduling

### Option 1: GitHub Actions (Recommended)
The repository includes a GitHub Actions workflow that runs daily at 6 AM UTC:

1. **Enable in GitHub**:
   - Go to your repository settings
   - Enable GitHub Actions
   - Add secrets:
     - `THESPORTSDB_API_KEY`: `123`
     - `APISPORTS_API_KEY`: `your_api_sports_key`

2. **Manual trigger**:
   - Go to Actions tab in GitHub
   - Select "Auto Update Upcoming Games"
   - Click "Run workflow"

### Option 2: Local Cron (Linux/Mac)
```bash
# Edit crontab
crontab -e

# Add daily update at 6 AM
0 6 * * * cd /path/to/your/project && python scripts/simple_auto_update.py >> auto_update.log 2>&1
```

### Option 3: Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 6:00 AM
4. Action: Start a program
5. Program: `python`
6. Arguments: `scripts/simple_auto_update.py`
7. Start in: `C:\path\to\your\project`

## 🏆 Supported Leagues

| League | API Provider | Status | Notes |
|--------|-------------|--------|-------|
| Rugby Championship | API-Sports | ✅ | Requires API key |
| Rugby World Cup | TheSportsDB | ✅ | Works with free key |
| United Rugby Championship | TheSportsDB | ⚠️ | May need premium key |
| Currie Cup | TheSportsDB | ⚠️ | May need premium key |

## 📊 Script Options

### Command Line Options
```bash
python scripts/simple_auto_update.py [OPTIONS]

Options:
  --db DB                    SQLite database path (default: data.sqlite)
  --days-ahead DAYS_AHEAD    Number of days ahead to look (default: 30)
  --leagues [LEAGUES ...]    Specific league IDs to update
  --dry-run                  Show what would be imported without changes
  --verbose, -v              Enable verbose logging
```

### Examples
```bash
# Update next 60 days
python scripts/simple_auto_update.py --days-ahead 60

# Update only Rugby Championship
python scripts/simple_auto_update.py --leagues 4986

# Test what would be imported
python scripts/simple_auto_update.py --dry-run --verbose
```

## 🔍 Monitoring

### Log Files
- **GitHub Actions**: Check the Actions tab for logs
- **Local runs**: Logs appear in console and `auto_update.log`

### Database Verification
```bash
# Check what's in your database
python -c "
import sqlite3
conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM event WHERE home_win IS NULL')
upcoming = cursor.fetchone()[0]
print(f'Upcoming games in database: {upcoming}')
conn.close()
"
```

## 🛠️ Troubleshooting

### Common Issues

1. **"No API key found"**
   - Set the `APISPORTS_API_KEY` environment variable
   - Or use only TheSportsDB leagues: `--leagues 4574`

2. **"Could not find league"**
   - The free TheSportsDB key has limited access
   - Some leagues may need premium API keys

3. **"No upcoming events found"**
   - Normal for off-season periods
   - Check if the league is currently active

4. **Rate limiting**
   - The script includes built-in rate limiting
   - If you hit limits, wait and try again

### Debug Mode
```bash
# Enable detailed logging
python scripts/simple_auto_update.py --verbose --dry-run
```

## 📈 Integration with Streamlit App

The automated updates work seamlessly with your Streamlit app:

1. **Run the update script** (manually or via scheduler)
2. **New games appear** in the Streamlit app automatically
3. **Predictions are generated** for new upcoming games
4. **No app restart needed**

## 🔄 Update Frequency

**Recommended schedule**:
- **Daily**: During active seasons
- **Weekly**: During off-seasons
- **Before major tournaments**: Run manually

## 📝 Notes

- The script only adds new games, it doesn't modify existing ones
- Games are automatically filtered to avoid duplicates
- Team information is created automatically if missing
- The script respects API rate limits and includes retry logic

## 🆘 Support

If you encounter issues:
1. Check the logs for error messages
2. Verify API keys are set correctly
3. Test with `--dry-run` first
4. Check if the league is currently active

---

**Happy predicting! 🏉**
