#!/usr/bin/env python3
"""
SIMPLIFIED: Basic Streamlit app for debugging Streamlit Cloud
"""

import streamlit as st

st.title("🏈 Hello Rugby AI!")
st.write("This ہے a basic Streamlit test.")

if st.button("Test Button"):
    st.success("✅ Streamlit is working!")

st.info("🎯 If you see this, Streamlit Cloud basic functionality works!")

# Simple test of our dependencies
try:
    import pandas as pd
    import numpy as np 
    import sqlite3
    import pickle
    st.success("✅ Core libraries imported successfully")
    
    # Test database
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    st.success(f"✅ Database connected - Tables: {tables}")
    conn.close()
    
except Exception as e:
    st.error(f"❌ Error: {e}")

def main():
    pass

if __name__ == "__main__":
    main()