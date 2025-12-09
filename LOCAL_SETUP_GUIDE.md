# Local Setup Guide - Rugby AI Predictor

This app can be run locally in two ways:

## Option 1: React Frontend (Recommended) ⚛️

This runs the React frontend which connects to Firebase Functions in the cloud.

### Prerequisites
- **Node.js** and **npm** installed
- Firebase Functions already deployed (or deploy them first)

### Steps

1. **Navigate to the public directory:**
   ```powershell
   cd public
   ```

2. **Install dependencies:**
   ```powershell
   npm install
   ```

3. **Start the development server:**
   ```powershell
   npm start
   ```

4. **Open your browser:**
   - The app will automatically open at `http://localhost:3000`
   - If it doesn't, manually navigate to that URL

### What Works
- ✅ League selection
- ✅ Match predictions (calls Firebase Functions)
- ✅ Upcoming matches
- ✅ Live matches
- ✅ League metrics

**Note:** The React app connects to Firebase Functions deployed in the cloud. Make sure your Firebase Functions are deployed for full functionality.

---

## Option 2: Python Streamlit App 🐍

This runs a standalone Python web app locally.

### Prerequisites
- **Python 3.11+** installed
- Virtual environment capability

### Steps

1. **Create and activate virtual environment:**
   
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

2. **Install Python dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Set up API keys (Optional but recommended):**
   
   **Windows (PowerShell):**
   ```powershell
   $env:SPORTDEVS_API_KEY="your_key_here"
   $env:THESPORTSDB_API_KEY="your_key_here"
   ```
   
   Or create `.streamlit/secrets.toml` file (see `secrets.toml.example`)

4. **Run the Streamlit app:**
   ```powershell
   streamlit run app.py
   ```
   
   Alternative entry points:
   ```powershell
   streamlit run expert_ai_app.py
   streamlit run enhanced_app.py
   ```

5. **Open your browser:**
   - The app will automatically open at `http://localhost:8501`
   - Check terminal output for the actual URL if 8501 is busy

### Required Files
Make sure these exist in the project root:
- ✅ `data.sqlite` - Database file
- ✅ `artifacts/` or `artifacts_optimized/` - Model files folder
- ✅ `prediction/` - Prediction modules folder

---

## Quick Start (React Frontend)

If you want the fastest setup for the React app:

```powershell
cd public
npm install
npm start
```

That's it! The app should open in your browser at `http://localhost:3000`.

---

## Troubleshooting

### React App Issues

**Port 3000 already in use:**
- The app will prompt you to use a different port
- Or stop the other process using port 3000

**Module not found errors:**
- Make sure you're in the `public` directory
- Run `npm install` again

**Firebase Functions not working:**
- Check browser console (F12) for errors
- Verify functions are deployed to Firebase
- Check function logs in Firebase Console

### Streamlit App Issues

**Python version issues:**
- Make sure Python 3.11+ is installed
- Check with: `python --version`

**Module not found:**
- Activate your virtual environment first
- Reinstall dependencies: `pip install -r requirements.txt`

**Database/Model files missing:**
- The app needs `data.sqlite` and model files in `artifacts/` or `artifacts_optimized/`
- Check if these files exist in the project root

**Port 8501 busy:**
- Streamlit will automatically try the next available port
- Check terminal output for the actual URL

---

## Which Option Should I Use?

- **Use React Frontend** if:
  - You want a modern web UI
  - Firebase Functions are already deployed
  - You want to develop the frontend

- **Use Streamlit** if:
  - You want everything running locally
  - You're developing Python/ML features
  - You prefer Python-based UI development

