# Enhanced Rugby AI Prediction System with Highlightly API Integration

## 🚀 New Features Added

### 📡 Highlightly API Integration
- **Live Scores**: Real-time match data and scores
- **Live Odds**: Current betting odds from multiple bookmakers
- **Team Statistics**: Detailed team performance metrics
- **Head-to-Head**: Historical matchups between teams
- **Highlights**: Match highlights and video content
- **Standings**: Current league standings

### 🎯 Enhanced Predictions
- **AI + Live Data**: Combines your trained AI models with real-time API data
- **Higher Accuracy**: More data sources = better predictions
- **Confidence Scoring**: Dynamic confidence based on available data
- **Live Match Tracking**: See live/upcoming matches with predictions

## 🔧 Setup Instructions

### 1. Environment Variables
Add your Highlightly API key to your environment:

```bash
# For local development
export HIGHLIGHTLY_API_KEY="your_api_key_here"

# For Streamlit Cloud
# Add to Secrets: HIGHLIGHTLY_API_KEY = "your_api_key_here"
```

### 2. New Files Added
- `prediction/highlightly_client.py` - Highlightly API client
- `prediction/enhanced_predictor.py` - Enhanced prediction system
- `enhanced_app.py` - New Streamlit app with live data

### 3. Usage

#### Basic AI Predictions (Existing)
```python
from prediction.hybrid_predictor import HybridPredictor

predictor = HybridPredictor('data.sqlite')
prediction = predictor.predict_match(
    "South Africa", "New Zealand", 4986, "2025-10-06"
)
```

#### Enhanced Predictions (New)
```python
from prediction.enhanced_predictor import EnhancedRugbyPredictor

enhanced_predictor = EnhancedRugbyPredictor('data.sqlite', 'your_api_key')
prediction = enhanced_predictor.get_enhanced_prediction(
    "South Africa", "New Zealand", 4986, "2025-10-06"
)
```

## 📊 What You Get

### Enhanced Predictions Include:
1. **AI Model Prediction** (your existing 67.3% accuracy)
2. **Live Odds** from multiple bookmakers
3. **Team Form** (last 5 games with win rates)
4. **Head-to-Head History** between teams
5. **Match Highlights** and video content
6. **Current Standings** for context
7. **Dynamic Confidence** scoring

### Live Data Features:
- **Real-time Match States**: See which games are live
- **Live Scores**: Current scores for ongoing matches
- **Upcoming Fixtures**: Next matches with predictions
- **League Coverage**: All major rugby leagues

## 🎮 How to Use

### Option 1: Enhanced Streamlit App
```bash
streamlit run enhanced_app.py
```

### Option 2: Update Existing App
Add to your existing `app.py`:
```python
from prediction.enhanced_predictor import EnhancedRugbyPredictor

# Load enhanced predictor
enhanced_predictor = EnhancedRugbyPredictor('data.sqlite', os.getenv('HIGHLIGHTLY_API_KEY'))

# Get enhanced prediction
prediction = enhanced_predictor.get_enhanced_prediction(
    home_team, away_team, league_id, match_date
)
```

## 🔄 Integration with Existing System

The enhanced system is **backward compatible**:
- ✅ Your existing AI models still work
- ✅ Your current accuracy (67.3%) is maintained
- ✅ All existing features preserved
- ✅ New features are additive

## 📈 Expected Improvements

With Highlightly API integration:
- **Better Context**: Team form, head-to-head, live odds
- **Higher Confidence**: More data sources = better confidence scoring
- **Live Updates**: Real-time match data
- **Enhanced UX**: Rich visualizations and live data

## 🚀 Next Steps

1. **Set up API key** in your environment
2. **Test the enhanced app**: `streamlit run enhanced_app.py`
3. **Deploy to Streamlit Cloud** with the new API key
4. **Monitor performance** with live data integration

Your rugby prediction system is now **significantly more powerful** with real-time data integration! 🏉🤖
