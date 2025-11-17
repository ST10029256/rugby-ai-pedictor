# How to Run the Rugby AI Predictor App

This is a Streamlit web application for rugby match predictions. Follow these steps to run it:

## Prerequisites

- **Python 3.11+** (recommended)
- **Windows/Linux/Mac** with terminal access

## Step 1: Set Up Virtual Environment

Create and activate a virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Configure API Keys (Optional but Recommended)

The app works without API keys, but enhanced features require them:

### Option A: Environment Variables (Recommended)

Set these environment variables before running:

**Windows (PowerShell):**
```powershell
$env:SPORTDEVS_API_KEY="your_key_here"
$env:THESPORTSDB_API_KEY="your_key_here"  # Free key is "123" but limited
$env:APISPORTS_API_KEY="your_key_here"     # Optional
```

**Windows (Command Prompt):**
```cmd
set SPORTDEVS_API_KEY=your_key_here
set THESPORTSDB_API_KEY=your_key_here
set APISPORTS_API_KEY=your_key_here
```

**Linux/Mac:**
```bash
export SPORTDEVS_API_KEY="your_key_here"
export THESPORTSDB_API_KEY="your_key_here"
export APISPORTS_API_KEY="your_key_here"
```

### Option B: Streamlit Secrets File (For Local Development)

1. Create `.streamlit` folder in the project root:
   ```bash
   mkdir .streamlit
   ```

2. Copy the example secrets file:
   ```bash
   copy secrets.toml.example .streamlit\secrets.toml
   ```
   (Linux/Mac: `cp secrets.toml.example .streamlit/secrets.toml`)

3. Edit `.streamlit/secrets.toml` and add your API keys

## Step 4: Verify Required Files

Make sure these files exist:
- ✅ `data.sqlite` - Database file (should exist)
- ✅ `artifacts/` or `artifacts_optimized/` - Model files folder
- ✅ `prediction/` - Prediction modules folder

## Step 5: Run the Application

**Main entry point (recommended):**
```bash
streamlit run app.py
```

**Alternative entry points:**
```bash
streamlit run expert_ai_app.py
streamlit run enhanced_app.py
```

The app will start and automatically open in your default web browser at:
**http://localhost:8501**

## Troubleshooting

### Error: "Module not found"
- Make sure your virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`

### Error: "Database file not found"
- Ensure `data.sqlite` exists in the project root
- If missing, you may need to run data collection scripts first

### Error: "Model files not found"
- Check that `artifacts/` or `artifacts_optimized/` folders exist
- Models should be `.pkl` files like `league_4446_model.pkl`

### Error: "XGBoost import failed"
- Try: `pip install --upgrade xgboost`
- On some systems, you may need: `pip install xgboost --no-cache-dir`

### Port Already in Use
If port 8501 is busy, Streamlit will try the next available port. Check the terminal output for the actual URL.

### API Key Issues
- The app will work without API keys but with limited features
- Check terminal output for warnings about missing API keys
- Free TheSportsDB key is `"123"` but has rate limits

## Features

Once running, you can:
- 🏉 Select a rugby league (URC, Currie Cup, etc.)
- 🎯 Enter match details (home team, away team, date)
- 🤖 Get AI-powered predictions
- 📊 View prediction confidence and scores
- 📈 See live odds and team form (if API keys configured)

## Stopping the App

Press `Ctrl+C` in the terminal to stop the Streamlit server.


