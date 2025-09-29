#!/usr/bin/env python3
"""
Main Entry Point for Streamlit Cloud Deployment
Directly runs the optimized rugby prediction app
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
        
except Exception as e:
    import streamlit as st
    
    st.set_page_config(page_title="Rugby Predictions", layout="wide", initial_sidebar_state="expanded")
    
    st.title("🏈 Enhanced Rugby AI Prediction System")
    st.write("---")
    
    st.error(f"🚨 **Deployment Error**: {e}")
    st.info("**Troubleshooting Steps:**")
    st.write("1. Check that all dependencies are installed")
    st.write("2. Verify the database file exists (`data.sqlite`)")  
    st.write("3. Ensure trained models are in the `artifacts/` folder")
    st.write("4. Check console for additional error details")
    
    # Show helpful debug info
    with st.expander("🔧 Debug Information"):
        st.write(f"**Project Root**: `{project_root}`")
        st.write(f"**Python Path**: `{sys.path[:3]}`")
        
        # Check if key files exist
        key_files = ['data.sqlite', 'artifacts/model_registry.json']
        for file in key_files:
            exists = "✅" if os.path.exists(file) else "❌"
            st.write(f"{exists} {file}")
