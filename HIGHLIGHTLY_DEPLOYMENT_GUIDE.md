# 🚀 Highlightly API Integration - Deployment Guide

## 📋 Overview
Your rugby prediction system now integrates with Highlightly API to provide:
- **Live odds** from multiple bookmakers
- **Team lineups** and player statistics  
- **Current standings** and league positions
- **Head-to-head history** between teams
- **Match highlights** and video content
- **Real-time match states** (live scores, upcoming fixtures)

## 🔧 Setup Instructions

### 1. Environment Variables

#### For Local Development:
```bash
export HIGHLIGHTLY_API_KEY="your_api_key_here"
```

#### For Streamlit Cloud:
1. Go to your Streamlit Cloud dashboard
2. Select your app
3. Go to "Settings" → "Secrets"
4. Add:
```toml
HIGHLIGHTLY_API_KEY = "your_api_key_here"
```

#### For GitHub Actions:
1. Go to your GitHub repository
2. Go to "Settings" → "Secrets and variables" → "Actions"
3. Add new repository secret:
   - Name: `HIGHLIGHTLY_API_KEY`
   - Value: `your_api_key_here`

### 2. Files Modified/Added

#### New Files:
- `prediction/highlightly_client.py` - API client
- `prediction/enhanced_predictor.py` - Enhanced prediction system
- `enhanced_app.py` - New Streamlit app with live data

#### Modified Files:
- `expert_ai_app.py` - Enhanced with Highlightly integration
- `requirements.txt` - Added plotly dependency
- `.github/workflows/check-for-updates.yml` - Added API key
- `.github/workflows/auto-retrain-all-leagues.yml` - Added API key

### 3. Deployment Steps

#### Option A: Update Existing App (Recommended)
Your existing `expert_ai_app.py` has been enhanced with Highlightly integration. Just add the API key to your environment and deploy.

#### Option B: Use New Enhanced App
```bash
streamlit run enhanced_app.py
```

## 🎯 What You Get

### Enhanced Predictions Include:
1. **AI Model Prediction** (your existing 67.3% accuracy)
2. **Live Odds** from multiple bookmakers
3. **Team Form** (last 5 games with win rates)
4. **Head-to-Head History** between teams
5. **Match Highlights** and video content
6. **Current Standings** for context
7. **Dynamic Confidence** scoring

### Live Features:
- **Real-time Match States**: See which games are live
- **Live Scores**: Current scores for ongoing matches
- **Upcoming Fixtures**: Next matches with predictions
- **League Coverage**: All major rugby leagues

## 📊 AI Decision Making with Odds

The AI now makes decisions based on:

### 1. **Odds Analysis**
- Compares AI prediction with bookmaker odds
- Identifies value bets (AI disagrees with odds)
- Adjusts confidence based on odds consensus

### 2. **Team Form Integration**
- Last 5 games performance
- Win rates and scoring patterns
- Recent momentum trends

### 3. **Head-to-Head Context**
- Historical matchups
- Previous score patterns
- Team-specific advantages

### 4. **Standings Context**
- Current league positions
- Playoff implications
- Motivation factors

## 🔄 GitHub Actions Integration

Your workflows now include Highlightly API:

### Check for Updates Workflow:
- Fetches live match data
- Updates database with real-time information
- Triggers retraining when new data is available

### Retrain Models Workflow:
- Uses live data for enhanced training
- Incorporates odds and form data
- Deploys updated models automatically

## 🎮 Usage Examples

### Enhanced Prediction:
```python
from prediction.enhanced_predictor import EnhancedRugbyPredictor

predictor = EnhancedRugbyPredictor('data.sqlite', 'your_api_key')
prediction = predictor.get_enhanced_prediction(
    "South Africa", "New Zealand", 4986, "2025-10-06"
)

# Prediction now includes:
# - AI model output
# - Live odds from bookmakers
# - Team form data
# - Head-to-head history
# - Enhanced confidence scoring
```

### Live Matches:
```python
live_matches = predictor.get_live_matches(league_id=4446)
# Returns live/upcoming matches with predictions
```

## 🚨 Troubleshooting

### Common Issues:

1. **API Key Not Working**
   - Check key is correct
   - Verify environment variable is set
   - Check API quota limits

2. **No Live Data**
   - API might be rate limited
   - Check internet connection
   - Verify league mapping

3. **Predictions Not Enhanced**
   - Check Highlightly API availability
   - Verify team name matching
   - Check date format

### Debug Mode:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📈 Expected Improvements

With Highlightly API integration:
- **Better Context**: Team form, head-to-head, live odds
- **Higher Confidence**: More data sources = better confidence scoring
- **Live Updates**: Real-time match data
- **Enhanced UX**: Rich visualizations and live data
- **Smarter AI**: Decisions based on odds, form, and standings

## 🎉 Next Steps

1. **Set up API key** in your environment
2. **Test locally**: `streamlit run expert_ai_app.py`
3. **Deploy to Streamlit Cloud** with the new API key
4. **Monitor performance** with live data integration
5. **Enjoy enhanced predictions** with odds-based decision making!

Your rugby prediction system is now **significantly more powerful** with real-time data integration and AI decisions based on odds, lineups, and standings! 🏉🤖✨
