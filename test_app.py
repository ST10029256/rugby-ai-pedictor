#!/usr/bin/env python3
"""
Simple test app to verify Streamlit Cloud deployment
"""

import streamlit as st
import os
import sys

st.set_page_config(
    page_title="Test App",
    layout="wide",
    page_icon="🧪"
)

st.title("🧪 Streamlit Cloud Test App")
st.write("If you can see this, your Streamlit Cloud deployment is working!")

# Test basic functionality
st.subheader("Environment Check")
st.write(f"Python version: {sys.version}")
st.write(f"Current directory: {os.getcwd()}")

# Test file access
st.subheader("File Access Test")
files_to_check = [
    "expert_ai_app.py",
    "requirements.txt",
    "data.sqlite",
    "artifacts/league_4446_model.pkl",
    "artifacts_optimized/league_4446_model_optimized.pkl"
]

for file_path in files_to_check:
    exists = os.path.exists(file_path)
    status = "✅" if exists else "❌"
    st.write(f"{status} {file_path}")

# Test imports
st.subheader("Import Test")
try:
    import pandas as pd
    st.write("✅ pandas imported successfully")
except ImportError as e:
    st.write(f"❌ pandas import failed: {e}")

try:
    import numpy as np
    st.write("✅ numpy imported successfully")
except ImportError as e:
    st.write(f"❌ numpy import failed: {e}")

try:
    import sqlite3
    st.write("✅ sqlite3 imported successfully")
except ImportError as e:
    st.write(f"❌ sqlite3 import failed: {e}")

try:
    from prediction.features import FeatureConfig
    st.write("✅ prediction.features imported successfully")
except ImportError as e:
    st.write(f"❌ prediction.features import failed: {e}")

st.success("Test app is working! You can now deploy the main app.")
