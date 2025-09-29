#!/usr/bin/env python3
"""
Minimal test app for Streamlit Cloud debugging
"""

import streamlit as st

st.set_page_config(
    page_title="Rugby AI Test", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏈 Rugby AI Prediction System - Test")

st.write("This is a minimal test version to diagnose Streamlit Cloud issues.")

# Test basic imports
try:
    import pandas as pd
    import numpy as np
    import sqlite3
    import pickle
    st.success("✅ Core libraries imported successfully")
except Exception as e:
    st.error(f"❌ Import error: {e}")

# Test database connection
try:
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    st.success(f"✅ Database connected - Tables: {tables}")
    conn.close()
except Exception as e:
    st.error(f"❌ Database error: {e}")

# Test model loading
try:
    import pickle
    models = []
    for league in [4446, 4574, 4986, 5069]:
        try:
            with open(f'artifacts/league_{league}_model.pkl', 'rb') as f:
                model = pickle.load(f)
                models.append(f"League {league}: ✅")
        except Exception as e:
            models.append(f"League {league}: ❌ {str(e)[:50]}")
    
    st.write("**Model Status:**")
    for model in models:
        st.write(model)
        
except Exception as e:
    st.error(f"❌ Model loading error: {e}")

st.info("🚀 If you see this page with green checkmarks, Streamlit Cloud is working!")
st.info(f"📍 Ready to upgrade to full AI prediction system!")
