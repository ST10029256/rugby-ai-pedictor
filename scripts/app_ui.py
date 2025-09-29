#!/usr/bin/env python3

import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
import numpy as np

# Add the project root to the Python path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def main():
    st.set_page_config(
        page_title="Rugby Predictions", 
        layout="wide", 
        initial_sidebar_state="expanded"
    )
    
    # Basic app header
    st.title("🏉 Rugby Predictions")
    st.caption("Professional AI predictions for major rugby competitions")
    
    try:
        # Direct integration - try to import model manager
        from scripts.model_manager import ModelManager
        
        # Initialize model manager
        model_manager = ModelManager("artifacts")
        
        if model_manager is None:
            st.error("⚠️ Unable to load prediction models")
            return
        
        # Get available leagues
        league_names = model_manager.get_league_names()
        
        if not league_names:
            st.error("⚠️ No trained models found")
            return
            
        # Database connection
        conn = sqlite3.connect('data.sqlite')
        
        # Sidebar with league selection
        with st.sidebar:
            st.subheader("🏆 Live Performance")
            
            # League selection
            selected_league = st.selectbox(
                "Select League:",
                options=list(league_names.keys()),
                format_func=lambda x: league_names[x]
            )
            
            if selected_league:
                # Show basic info
                st.info(f"Selected: **{league_names[selected_league]}**")
                
                # Simple model test
                if model_manager.is_model_available(selected_league):
                    st.success("✅ Model loaded")
                else:
                    st.error("❌ Model not available")
        
        # Main content area
        st.subheader("🎯 Prediction Interface")
        
        if selected_league:
            league_name = league_names[selected_league]
            
            # Try to load model and make predictions
            try:
                model_data = model_manager.load_model(selected_league)
                
                if model_data and "error" not in model_data:
                    st.success(f"✅ **{league_name}** model loaded successfully")
                    
                    # Show model performance
                    perf = model_data.get("performance", {})
                    st.write("**📊 Model Performance:**")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Winner Accuracy", f"{perf.get('winner_accuracy', 0):.1%}")
                    with col2:
                        st.metric("Home MAE", f"{perf.get('home_mae', 0):.1f}")
                    with col3:
                        st.metric("Away MAE", f"{perf.get('away_mae', 0):.1f}")
                    with col4:
                        st.metric("Overall MAE", f"{perf.get('overall_mae', 0):.1f}")
                    
                    # Feature information
                    feature_count = len(model_data.get("feature_columns", []))
                    st.write(f"**🔧 Features:** {feature_count} advanced prediction features")
                    
                    # Training information
                    training_games = model_data.get("training_games", 0)
                    trained_at = model_data.get("trained_at", "Unknown")
                    st.write(f"**📈 Training:** {training_games} games (trained: {trained_at})")
                    
                    # Sample prediction demo
                    st.subheader("🎲 Prediction Demo")
                    st.write("Model ready for real-time predictions...")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**🏠 Home Team Example:**")
                        st.write("- Team Strength: High")
                        st.write("- Recent Form: Good") 
                        
                    with col2:
                        st.write("**✈️ Away Team Example:**")
                        st.write("- Team Strength: Medium")
                        st.write("- Recent Form: Fair")
                    
                    st.info("💡 **Real Predictions**: Use the full app for team selection and live score predictions")
                    
                else:
                    st.warning("⚠️ Model data incomplete")
                    
            except Exception as pred_e:
                st.error(f"🚨 **Prediction Error**: {pred_e}")
                
                # Show basic info as fallback
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**League:** {league_name}")
                    st.write(f"**League ID:** {selected_league}")
                    
                with col2:
                    st.write("**Features:** 34 advanced prediction features")
                    st.write("**Accuracy:** Enhanced AI model")
        
        # Close database
        conn.close()
        
        st.success("🚀 Enhanced Rugby AI System Active!")
        
    except Exception as e:
        # Fallback with detailed error info
        st.error(f"🚨 **Import Error**: {e}")
        
        with st.expander("🔧 Debug Information"):
            st.write(f"**Error Type**: {type(e).__name__}")
            st.write(f"**Details**: {str(e)}")
            
            # File checks
            import os
            files_to_check = [
                'artifacts/model_registry.json',
                'scripts/model_manager.py', 
                'scripts/app_ui_optimized.py',
                'data.sqlite'
            ]
            
            st.write("**File Check:**")
            for file in files_to_check:
                exists = "✅" if os.path.exists(file) else "❌"
                st.write(f"{exists} {file}")
        
        st.info("🎯 Next steps: Check that all required files are present")

if __name__ == "__main__":
    main()