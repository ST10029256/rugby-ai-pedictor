# Python Version Compatibility Issue

## Problem
You're using Python 3.14, but Firebase Cloud Functions officially support Python 3.11. The protobuf library has compatibility issues with Python 3.14.

## Solution: Use Python 3.11

### Option 1: Create a new virtual environment with Python 3.11

1. **Install Python 3.11** (if not already installed):
   - Download from: https://www.python.org/downloads/release/python-3110/
   - Or use pyenv: `pyenv install 3.11.0`

2. **Remove the current venv and create a new one**:
   ```powershell
   cd rugby-ai-predictor
   Remove-Item -Recurse -Force venv
   python3.11 -m venv venv
   .\venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Deploy again**:
   ```powershell
   firebase deploy --only functions
   ```

### Option 2: Update protobuf (may not fully fix the issue)

I've updated `requirements.txt` to use `protobuf>=5.0.0`, but Python 3.14 support is still experimental. Try:

```powershell
cd rugby-ai-predictor
.\venv\Scripts\activate
pip install --upgrade protobuf
pip install -r requirements.txt
```

### Recommended: Use Python 3.11

Firebase Functions officially supports:
- Python 3.11 ✅ (Recommended)
- Python 3.10 ✅
- Python 3.9 ✅

Python 3.14 is too new and may have compatibility issues with various libraries.

