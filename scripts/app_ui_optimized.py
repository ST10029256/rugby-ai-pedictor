from __future__ import annotations

import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from typing import Any, cast

import streamlit as st

# Add the project root to the Python path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig
from scripts.model_manager import ModelManager

def safe_to_float(value: Any, default: float = 0.0) -> float:
    import numpy as np  # Local import for type checking
    
    if value is None:
        return default
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return float(value)
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        v = float(value)
        if np.isnan(v):
            return default
        return v
    except Exception:
        return default

def safe_to_int(value: Any, default: int = 0) -> int:
    import numpy as np  # Local import for type checking
    
    if value is None:
        return default
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return int(value)
    try:
        return int(value)
    except Exception:
        return default

@st.cache_resource
def load_model_manager():
    """Load the model manager with caching"""
    # Get the project root directory to ensure correct path resolution
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, os.pardir))
    artifacts_path = os.path.join(project_root, 'artifacts')
    
    # Verify artifacts directory exists
    if not os.path.exists(artifacts_path):
        st.error(f"❌ Artifacts directory not found at: {artifacts_path}")
        st.error(f"Current working directory: {os.getcwd()}")
        # Try to find any artifacts directory
        for root, dirs, files in os.walk(os.getcwd()):
            if 'artifacts' in dirs:
                found_path = os.path.join(root, 'artifacts')
                st.error(f"Found artifacts directory at: {found_path}")
                artifacts_path = found_path
                break
        else:
            return None
    
    return ModelManager(artifacts_path)

def main() -> None:
    st.set_page_config(
        page_title="Rugby Predictions", 
        layout="wide", 
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': 'https://github.com/your-repo',
            'Report a bug': "https://github.com/your-repo/issues",
            'About': "# Rugby Predictions\nAI-powered rugby match predictions!"
        }
    )
    
    # Comprehensive console warning suppression script
    st.markdown("""
    <script>
        // Immediately suppress ALL browser feature warning patterns
        (function() {
            const originalWarn = console.warn;
            const originalError = console.error;
            const originalLog = console.log;
            
            const blockedPatterns = [
                'Unrecognized feature:',
                'ambient-light-sensor',
                'battery',
                'document-domain', 
                'layout-animations',
                'legacy-image-formats',
                'oversized-images',
                'vr',
                'wake-lock',
                'iframe which has both allow-scripts and allow-same-origin',
                'INITIAL ->',
                'RUNNING',
                'Pe @ index-B59N3yFD.js',
                'index-B59N3yFD.js:',
                'An iframe which has both allow-scripts and allow-same-origin for its sandbox attribute can escape its sandboxing'
            ];
            
            function shouldBlockMessage(msg) {
                if (typeof msg !== 'string') return false;
                const lowerMsg = msg.toLowerCase();
                return blockedPatterns.some(pattern => 
                    lowerMsg.includes(pattern.toLowerCase()) || lowerMsg.includes(pattern)
                );
            }
            
            console.warn = function() {
                const msg = Array.from(arguments).join(' ');
                if (shouldBlockMessage(msg)) return;
                originalWarn.apply(console, arguments);
            };
            
            console.error = function() {
                const msg = Array.from(arguments).join(' ');
                if (shouldBlockMessage(msg)) return;
                originalError.apply(console, arguments);
            };
            
            console.log = function() {
                const msg = Array.from(arguments).join(' ');
                if (shouldBlockMessage(msg)) return;
                originalLog.apply(console, arguments);
            };
            
            // Clear any existing warnings immediately
            setTimeout(() => console.clear(), 100);
            
            console.info('🔧 Enhanced Console Filter: Active - Blocking browser feature warnings');
        })();
    </script>
    """, unsafe_allow_html=True)
    
    # Add comprehensive security headers after script
    st.markdown("""
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
        <meta http-equiv="Permissions-Policy" content="ambient-light-sensor=(), battery=(), document-domain=(), layout-animations=(self), legacy-image-formats=(self), oversized-images=(self), vr=(self), wake-lock=()">
        <meta http-equiv="Content-Security-Policy" content="frame-ancestors 'self'; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';">
        <meta http-equiv="X-Frame-Options" content="SAMEORIGIN">
        <meta http-equiv="X-Content-Type-Options" content="nosniff">
    </head>
    """, unsafe_allow_html=True)
    
    # Add enhanced CSS for mobile responsiveness
    st.markdown("""
    <style>
    /* Suppress browser warnings */
    html { 
        overflow-x: hidden; 
    }
    
    body {
        overscroll-behavior: none;
        touch-action: manipulation;
    }
    
    /* Global mobile optimizations */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    /* Mobile-first responsive design */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        /* Typography adjustments */
        .stSelectbox > div > div,
        .stRadio > div > div {
            font-size: 14px;
        }
        
        .stDataFrame {
            font-size: 12px;
        }
        
        .stMarkdown h1 {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }
        
        .stMarkdown h2 {
            font-size: 1.2rem;
            margin-bottom: 0.75rem;
        }
        
        .stMarkdown h3 {
            font-size: 1rem;
            margin-bottom: 0.5rem;
        }
        
        /* Table optimizations */
        .stDataFrame table {
            font-size: 11px;
        }
        
        .stDataFrame th,
        .stDataFrame td {
            padding: 0.25rem 0.125rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        /* Mobile-friendly fixture cards */
        .fixture-card {
            background-color: #f8f9fa;
            padding: 1rem;
            border-radius: 0.75rem;
            margin: 1rem 0;
            border-left: 4px solid #1f77b4;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .fixture-card h4 {
            margin: 0 0 0.75rem 0;
            color: #1f77b4;
            font-size: 1.1rem;
            font-weight: 600;
        }
        
        .fixture-card p {
            margin: 0.5rem 0;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        
        .prediction-highlight {
            background: linear-gradient(135deg, #e8f4fd 0%, #f0f8ff 100%);
            padding: 0.75rem;
            border-radius: 0.5rem;
            margin: 0.75rem 0;
            border: 1px solid #1f77b4;
            box-shadow: 0 1px 3px rgba(31, 119, 180, 0.2);
        }
        
        /* Metric cards in sidebar */
        .metric-container {
            margin-bottom: 0.5rem;
        }
        
        /* Sidebar optimizations */
        .sidebar .sidebar-content {
            padding: 1rem 0.5rem;
        }
        
        .sidebar .sidebar-content .stSelectbox,
        .sidebar .sidebar-content .stRadio {
            margin-bottom: 1rem;
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            font-size: 0.9rem;
            padding: 0.5rem 0.75rem;
        }
        
        /* Button and input styling */
        .stButton > button {
            width: 100%;
            border-radius: 0.5rem;
        }
        
        /* Improve touch targets */
        .stRadio > div > label > div {
            padding: 0.5rem;
            margin: 0.25rem 0;
        }
        
        /* Success/warning/error message styling */
        .stSuccess {
            border-radius: 0.5rem;
            padding: 0.75rem;
        }
        
        .stWarning {
            border-radius: 0.5rem;
            padding: 0.75rem;
        }
        
        .stError {
            border-radius: 0.5rem;
            padding: 0.75rem;
        }
        
        .stInfo {
            border-radius: 0.5rem;
            padding: 0.75rem;
        }
    }
    
    /* Tablet optimizations */
    @media (min-width: 769px) and (max-width: 1024px) {
        .main .block-container {
            padding-left: 2rem;
            padding-right: 2rem;
        }
        
        .fixture-card {
            padding: 1.25rem;
        }
        
        .prediction-highlight {
            padding: 1rem;
        }
    }
    
    /* Desktop optimizations */
    @media (min-width: 1025px) {
        .main .block-container {
            padding-left: 3rem;
            padding-right: 3rem;
        }
    }
    
    /* Loading spinner optimization */
    .stSpinner {
        margin: 2rem auto;
    }
    
    /* Custom scrollbar for mobile */
    @media (max-width: 768px) {
        ::-webkit-scrollbar {
            width: 4px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #1f77b4;
            border-radius: 2px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🏉 Rugby Predictions")
    st.caption("🤖 AI-powered predictions that update automatically")

    # Initialize model manager
    model_manager = load_model_manager()
    
    if model_manager is None:
        st.error("❌ **Critical Error**: Unable to load model manager!")
        st.error("The artifacts directory or models could not be found.")
        st.stop()
    
    # Check if we have compatible models
    league_names = model_manager.get_league_names()
    compatible_leagues = []
    for league_id, league_name in league_names.items():
        if model_manager.is_model_available(league_id):
            compatible_leagues.append((league_id, league_name))
    
    if not compatible_leagues:
        st.error("⚠️ **Model Compatibility Issue**")
        st.error("None of the trained models are compatible with the current scikit-learn version.")
        st.info("🔄 **Solution**: This will be automatically resolved when Streamlit Cloud redeploys with the correct scikit-learn version.")
        st.info("📋 **Available Leagues**: All leagues are trained but require scikit-learn 1.5.2")
        return
    
    # Debug information (hidden by default)  
    debug_info = st.expander("🔍 Debug Information", expanded=False)
    with debug_info:
        registry_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'artifacts', 'model_registry.json')
        st.write(f"**Model Manager Status:** ✅ Loaded successfully")
        st.write(f"**Registry Path:** `{registry_path}`")
        st.write(f"**Current Directory:** `{os.getcwd()}`")
        st.write(f"**App Directory:** `{os.path.dirname(os.path.abspath(__file__))}`")
        
        # Model availability debugging
        st.write("**Model Availability Check:**")
        league_names = model_manager.get_league_names()
        for league_id, league_name in league_names.items():
            is_available = model_manager.is_model_available(league_id)
            model_file = f"/mount/src/rugby-ai-pedictor/artifacts/league_{league_id}_model.pkl"
            st.write(f"- **{league_name}** (ID: {league_id}): {'✅ Available' if is_available else '❌ Not Found'}")
            if not is_available:
                st.write(f"  Expected file: `{model_file}`")
        
        # Registry content
        registry_summary = model_manager.get_registry_summary()
        st.write(f"**Total Leagues in Registry:** {len(registry_summary.get('leagues', {}))}")
        
        # Environment information
        try:
            import sklearn
            st.write(f"**Scikit-learn Version:** {sklearn.__version__}")
        except ImportError:
            st.write("**Scikit-learn:** Not available")
        
        try:
            import numpy as np
            st.write(f"**NumPy Version:** {np.__version__}")
        except ImportError:
            st.write("**NumPy:** Not available")
    
    # Mobile-optimized sidebar
    with st.sidebar:
        st.subheader("📊 Model Status")
        registry_summary = model_manager.get_registry_summary()
        
        if "error" not in registry_summary:
            with st.expander("System Status", expanded=False):
                st.write(f"**Last Updated:** {registry_summary.get('last_updated', 'Unknown')}")
                st.write(f"**Total Leagues:** {registry_summary.get('total_leagues', 0)}")
                
                # Show league-specific status in a more compact format
                for league_id_key, info in registry_summary.get("leagues", {}).items():
                    league_name = info.get("name", f"League {league_id_key}")
                    accuracy = info.get("winner_accuracy", 0)
                    mae = info.get("overall_mae", 0)
                    st.metric(
                        label=league_name,
                        value=f"{accuracy:.1%}",
                        delta=f"MAE: {mae:.1f}"
                    )
        else:
            st.error("⚠️ Model registry unavailable")

        st.divider()
        
        # League selection with better mobile UX
        st.subheader("🏉 League Selection")
        league_name_to_id = {
            "Rugby Championship": 4986,
            "United Rugby Championship": 4446,
            "Currie Cup": 5069,
            "Rugby World Cup": 4574,
        }
        
        # Use radio buttons for better mobile experience
        league = st.radio(
            "Choose League",
            options=list(league_name_to_id.keys()),
            index=1,
            help="Select the league you want to see predictions for"
        )
        league_id = league_name_to_id[league]
    
    # Check if model is available
    if not model_manager.is_model_available(league_id):
        st.error(f"No trained model available for {league}. Please train models first.")
        st.info("Run `python scripts/train_models.py` to train models.")
        return

    # Load the trained model
    try:
        model_package = model_manager.load_model(league_id)
        if not model_package:
            st.error(f"❌ **Model Loading Failed** for {league}")
            st.error("This usually indicates a scikit-learn version compatibility issue.")
            st.info("💡 **Solution:** The models may have been trained with a different version of scikit-learn.")
            return
    except Exception as e:
        st.error(f"❌ **Critical Error** loading model for {league}: {str(e)}")
        st.error("Check the debug information for more details.")
        return

        # Show current model info in a more mobile-friendly format
        st.divider()
        st.subheader("🤖 Current Model")
        
        with st.expander(f"Model Details - {league}", expanded=False):
            st.metric(
                label="Training Date",
                value=model_package.get('trained_at', 'Unknown')
            )
            st.metric(
                label="Training Games",
                value=model_package.get('training_games', 0)
            )
            
            performance = model_package.get("performance", {})
            st.metric(
                label="Winner Accuracy",
                value=f"{performance.get('winner_accuracy', 0):.1%}"
            )
            st.metric(
                label="Score MAE",
                value=f"{performance.get('overall_mae', 0):.1f}"
            )

    # Neutral mode handled automatically by league
    neutral_mode = (league_id in {4574})
    elo_k = 24

    # Data and features
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.sqlite")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=float(elo_k), neutral_mode=bool(neutral_mode)))

    # Upcoming fixtures for selected league (future/today only)
    upcoming = df[df["home_win"].isna()].copy()
    upc = cast(pd.DataFrame, upcoming[upcoming["league_id"] == league_id].copy())
    if "date_event" in upc.columns:
        try:
            today = pd.Timestamp(pd.Timestamp.today().date())
            upc = upc.copy()
            upc["date_event"] = pd.to_datetime(upc["date_event"], errors="coerce")
            upc = cast(pd.DataFrame, upc[upc["date_event"] >= today])
        except Exception:
            pass

    # Historical data
    hist = cast(pd.DataFrame, df[(df["league_id"] == league_id) & df["home_win"].notna()].copy())

    # Get feature columns from the trained model
    feature_cols = model_package.get("feature_columns", [])
    if not feature_cols:
        st.error("No feature columns found in trained model")
        return

    # Team names for display
    team_name: dict[int, str] = {}
    try:
        rows_nm = conn.cursor().execute(
            """
            SELECT DISTINCT t.id, COALESCE(t.name, '')
            FROM team t
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = ?
            """,
            (league_id,),
        ).fetchall()
        for tid_raw, nm in rows_nm:
            tid = safe_to_int(tid_raw, default=-1)
            team_name[tid] = nm or f"Team {tid}"
    except Exception:
        pass

    # Prepare upcoming rows with the same features as training
    if len(upc) == 0:
        st.info("No upcoming fixtures for this league.")
        return

    upc = upc.copy()
    
    # Import numpy for this section
    import numpy as np
    
    # Add missing columns with default values
    for col in feature_cols:
        if col not in upc.columns:
            upc[col] = np.nan

    # Calculate derived features
    upc["elo_diff"] = upc["elo_diff"].where(upc["elo_diff"].notna(), upc["elo_home_pre"] - upc["elo_away_pre"])
    if "home_form" in upc.columns and "away_form" in upc.columns:
        upc["form_diff"] = upc["form_diff"].where(upc["form_diff"].notna(), upc["home_form"] - upc["away_form"])
    if "home_rest_days" in upc.columns and "away_rest_days" in upc.columns:
        upc["rest_diff"] = upc["rest_diff"].where(upc["rest_diff"].notna(), upc["home_rest_days"] - upc["away_rest_days"])
    if "home_goal_diff_form" in upc.columns and "away_goal_diff_form" in upc.columns:
        upc["goal_diff_form_diff"] = upc["goal_diff_form_diff"].where(upc["goal_diff_form_diff"].notna(), upc["home_goal_diff_form"] - upc["away_goal_diff_form"])
    
    # Calculate pair elo expectation
    upc["pair_elo_expectation"] = upc["pair_elo_expectation"].where(
        upc["pair_elo_expectation"].notna(),
        1.0 / (1.0 + 10 ** ((upc["elo_away_pre"] - upc["elo_home_pre"]) / 400.0)),
    )
    
    # Get team mappings from the trained model
    team_mappings = model_package.get("team_mappings", {})
    _home_wr_map = team_mappings.get("home_wr_map", {})
    _away_wr_map = team_mappings.get("away_wr_map", {})
    
    upc["home_wr_home"] = upc["home_wr_home"].where(upc["home_wr_home"].notna(), upc["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan"))))
    upc["away_wr_away"] = upc["away_wr_away"].where(upc["away_wr_away"].notna(), upc["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan"))))

    # Prepare features for prediction
    X_upc = upc[feature_cols].to_numpy()
    
    # Make predictions using the trained models
    prob_home_list = []
    pred_home_list = []
    pred_away_list = []
    
    for i in range(len(X_upc)):
        features = X_upc[i]
        
        # Predict winner probability
        home_prob, away_prob = model_manager.predict_winner_probability(league_id, features)
        prob_home_list.append(home_prob)
        
        # Predict scores
        home_score, away_score = model_manager.predict_scores(league_id, features)
        pred_home_list.append(home_score)
        pred_away_list.append(away_score)

    prob_home = np.array(prob_home_list)
    pred_home = np.array(pred_home_list)
    pred_away = np.array(pred_away_list)

    # Display table
    def _name(tid: Any) -> str:
        return team_name.get(safe_to_int(tid, -1), str(safe_to_int(tid, -1)))

    if "date_event" in upc.columns:
        date_series = upc["date_event"].astype(str)
    else:
        date_series = pd.Series([""] * len(upc), dtype=str)
    
    # Create mobile-friendly display data
    disp = pd.DataFrame({
        "Date": date_series,
        "Home": upc["home_team_id"].apply(_name),
        "Away": upc["away_team_id"].apply(_name),
        "Home Win %": np.round(prob_home * 100.0, 1),
        "Home Score": np.round(pred_home, 1),
        "Away Score": np.round(pred_away, 1),
        "Margin": np.round(pred_home - pred_away, 1),
        "Pick": [(_name(h) if prob_home[i] >= 0.5 else _name(a)) for i, (h, a) in enumerate(zip(upc["home_team_id"], upc["away_team_id"]))],
    })
    disp = disp.sort_values(["Date", "Home"], ignore_index=True)

    st.subheader(f"Upcoming fixtures — {league}")
    
    # Create mobile-responsive table with column configuration
    column_config = {
        "Date": st.column_config.TextColumn("Date", width="small"),
        "Home": st.column_config.TextColumn("Home Team", width="medium"),
        "Away": st.column_config.TextColumn("Away Team", width="medium"),
        "Home Win %": st.column_config.NumberColumn("Home Win %", format="%.1f%%", width="small"),
        "Home Score": st.column_config.NumberColumn("Home", format="%.1f", width="small"),
        "Away Score": st.column_config.NumberColumn("Away", format="%.1f", width="small"),
        "Margin": st.column_config.NumberColumn("Margin", format="%.1f", width="small"),
        "Pick": st.column_config.TextColumn("Pick", width="medium"),
    }
    
    st.dataframe(
        disp, 
        column_config=column_config,
        hide_index=True
    )

    # Per-fixture cards - mobile optimized
    st.subheader("Match Summaries")
    
    for i in range(len(disp)):
        row = disp.iloc[i]
        winner = row["Pick"]
        home_win_prob = float(row["Home Win %"])
        home_score = float(row["Home Score"])
        away_score = float(row["Away Score"])
        margin = float(row["Margin"])
        
        # Determine confidence level
        confidence = "High" if abs(home_win_prob - 50) > 15 else "Medium" if abs(home_win_prob - 50) > 5 else "Low"
        confidence_color = "#28a745" if confidence == "High" else "#ffc107" if confidence == "Medium" else "#dc3545"
        
        # Create mobile-friendly card
        st.markdown(f"""
        <div class="fixture-card">
            <h4>{row['Home']} vs {row['Away']}</h4>
            <p><strong>Date:</strong> {row['Date']}</p>
            <div class="prediction-highlight">
                <p><strong>Predicted Winner:</strong> <span style="color: {confidence_color};">{winner}</span></p>
                <p><strong>Predicted Score:</strong> {row['Home']} {home_score:.1f} - {away_score:.1f} {row['Away']}</p>
                <p><strong>Home Win Probability:</strong> {home_win_prob:.1f}%</p>
                <p><strong>Confidence:</strong> <span style="color: {confidence_color};">{confidence}</span></p>
                <p><strong>Expected Margin:</strong> {margin:+.1f}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Show retraining info
        st.divider()
        st.subheader("🔄 Auto-Retraining")
        st.info("Models automatically retrain after each completed match and push updates to GitHub.")
        
        # Console warning notice
        st.divider()
        with st.expander("ℹ️ About Console Warnings", expanded=False):
            st.markdown("""
            **If you see browser console warnings:**
            
            🔍 **What you're seeing**: Browser warnings from iframe embedding on Streamlit Cloud
            
            ✅ **Is this normal?** Yes! These are cosmetic warnings that don't affect app functionality
            
            🛠️ **How to hide them**: 
            - Press F12 → Console tab → Filter icon → Add "-iframe", "-sandbox", "-ambient", etc.
            - Or simply ignore them - they're harmless!
            
            📚 **More info**: See `CONSOLE_WARNINGS_GUIDE.md` for detailed explanations
            """)
            st.info("💡 **Tip**: These warnings only appear in development/professional environments. End users rarely notice affected applications.")

    conn.close()

if __name__ == "__main__":
    main()
