#!/usr/bin/env python3
"""
Main Entry Point for Streamlit Cloud Deployment
Redirects to the optimized rugby prediction app
"""

import os
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the optimized app
try:
    from scripts.app_ui_optimized import main
    
    if __name__ == "__main__":
        main()
        
except ImportError as e:
    print(f"Error importing optimized app: {e}")
    print("Falling back to basic app...")
    
    # Fallback - run a simple error message
    import streamlit as st
    
    st.set_page_config(page_title="Rugby Predictions", layout="wide")
    st.error("🚨 Application Error")
    st.write("Please check the deployment configuration.")
    st.write(f"Import error: {e}")
