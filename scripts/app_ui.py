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
    import streamlit as st
    
    try:
        # Set page config first
        st.set_page_config(
            page_title="Rugby AI Predictions", 
            layout="wide", 
            initial_sidebar_state="expanded"
        )
        
        # Test basic imports first
        try:
            import pandas as pd
            import numpy as np
            import sqlite3
            import pickle
        except ImportError as ie:
            st.error(f"❌ **Critical Import Error**: {ie}")
            st.stop()
        
        # Import the optimized app's main function
        from scripts.app_ui_optimized import main as optimized_main
        return optimized_main()
        
    except Exception as e:
        # Graceful fallback with detailed error info
        st.title("🏈 Enhanced Rugby AI Prediction System")
        st.write("---")
        
        st.error(f"🚨 **Deployment Error**: {e}")
        
        # Show debug information
        with st.expander("🔧 Debug Information"):
            st.write(f"**Error Type**: {type(e).__name__}")
            st.write(f"**Error Details**: {str(e)}")
            
            # Check key files
            import os
            key_files = [
                'data.sqlite',
                'artifacts/model_registry.json', 
                'scripts/app_ui_optimized.py',
                'prediction/features.py',
                'scripts/model_manager.py'
            ]
            
            st.write("**File Check:**")
            for file in key_files:
                exists = "✅" if os.path.exists(file) else "❌"
                st.write(f"{exists} {file}")
            
            # Check Python path
            import sys
            st.write(f"**Python Path**: {sys.path[:3]}")
        
        st.info("**Next Steps:**")
        st.write("1. Check that all files exist")
        st.write("2. Verify Streamlit Cloud has all dependencies")
        st.write("3. Check console logs for more details")
        
        return None

if __name__ == "__main__":
    main()
