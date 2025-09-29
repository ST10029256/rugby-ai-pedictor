#!/usr/bin/env python3

import streamlit as st
import os
import sys

# Add the project root to the Python path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def main():
    try:
        # Import the optimized app
        from scripts.app_ui_optimized import main as optimized_main
        return optimized_main()
        
    except Exception as e:
        # Show error with helpful debugging
        st.title("🏈 Enhanced Rugby AI Prediction System")
        st.write("---")
        
        st.error(f"🚨 **Deployment Error**: {e}")
        
        # Show what works
        st.success("✅ Streamlit Cloud is working!")
        st.info("🚀 Ready to restore full AI prediction system!")
        
        with st.expander("🔧 Debug Information"):
            st.write(f"**Error**: {type(e).__name__}: {str(e)}")
            
            # Test core functionality
            try:
                import pandas as pd
                import numpy as np
                import sqlite3
                import pickle
                st.write("✅ Core libraries imported successfully")
                
                # Test database
                conn = sqlite3.connect('data.sqlite')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM event")
                count = cursor.fetchone()[0]
                st.write(f"✅ Database: {count} events")
                conn.close()
                
            except Exception as db_e:
                st.write(f"❌ Database error: {db_e}")
        
        return None

if __name__ == "__main__":
    main()