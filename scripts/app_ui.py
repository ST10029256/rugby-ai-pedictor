#!/usr/bin/env python3
"""
Main Streamlit App Entry Point
Uses the optimized version with console warning suppression
"""

import os
import sys

# Add the project root to the Python path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run the optimized app
def main():
    try:
        # Import the optimized app's main function
        from scripts.app_ui_optimized import main as optimized_main
        return optimized_main()
    except ImportError as e:
        # Fallback: copy the optimized app code directly
        import streamlit as st
        
        st.set_page_config(
            page_title="Rugby Predictions", 
            layout="wide", 
            initial_sidebar_state="expanded"
        )
        
        st.title("🏈 Enhanced Rugby AI Prediction System")
        st.write("---")
        
        st.error(f"🚨 **Import Error**: {e}")
        st.info("**Troubleshooting:**")
        st.write("1. Check that scripts/app_ui_optimized.py exists")
        st.write("2. Verify all dependencies are installed")
        st.write("3. Check Python path configuration")
        
        return None

if __name__ == "__main__":
    main()
