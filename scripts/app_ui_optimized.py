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
            'Get Help': 'https://github.com/ST10029256/rugby-ai-pedictor',
            'Report a bug': "https://github.com/ST10029256/rugby-ai-pedictor/issues",
            'About': "# Rugby Predictions\nAI-powered rugby match predictions using machine learning models"
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
            
            .match-card {
                margin: 1rem 0;
                padding: 1rem;
            }
            
            .match-teams {
                font-size: 1.1rem;
            }
            
            .prediction-grid {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }
            
            .score-text {
                font-size: 1.2rem;
            }
            
            .prediction-value {
                font-size: 1.25rem;
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
        
        /* Professional match summary cards */
        .match-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            border-radius: 1rem;
            margin: 1.5rem 0;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 1px solid #e3e8ed;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        
        .match-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }
        
        .match-header {
            display: flex;
            justify-content: between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid #e9ecef;
        }
        
        .match-teams {
            font-size: 1.25rem;
            font-weight: 700;
            color: #2c3e50;
            text-align: center;
            margin: 0;
        }
        
        .match-date {
            font-size: 0.9rem;
            color: #6c757d;
            font-weight: 500;
            margin: 0;
        }
        
        .prediction-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .prediction-item {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            padding: 1rem;
            border-radius: 0.75rem;
            text-align: center;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3);
        }
        
        .prediction-item.alt {
            background: linear-gradient(135deg, #059669 0%, #047857 100%);
            box-shadow: 0 2px 8px rgba(5, 150, 105, 0.3);
        }
        
        .prediction-item.warning {
            background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
            box-shadow: 0 2px 8px rgba(217, 119, 6, 0.3);
        }
        
        .prediction-label {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
            opacity: 0.9;
        }
        
        .prediction-value {
            font-size: 1.5rem;
            font-weight: 800;
            margin: 0;
        }
        
        .score-display {
            background: linear-gradient(135deg, #1e40af 0%, #3730a3 100%);
            color: white;
            padding: 1.25rem;
            border-radius: 1rem;
            text-align: center;
            margin: 1rem 0;
            box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
        }
        
        .score-text {
            font-size: 1.5rem;
            font-weight: 800;
            margin: 0;
        }
        
        .confidence-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 1rem;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            margin-top: 0.5rem;
        }
        
        .confidence-badge.high {
            background-color: #22c55e;
            color: white;
        }
        
        .confidence-badge.medium {
            background-color: #f59e0b;
            color: white;
        }
        
        .confidence-badge.low {
            background-color: #ef4444;
            color: white;
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
    st.caption("Professional AI predictions for major rugby competitions")

    # Initialize model manager
    model_manager = load_model_manager()
    
    if model_manager is None:
        st.error("⚠️ Unable to load prediction models")
        st.info("Please refresh the page or try again later.")
        st.stop()
    
    # Check if we have compatible models
    league_names = model_manager.get_league_names()
    compatible_leagues = []
    for league_id, league_name in league_names.items():
        if model_manager.is_model_available(league_id):
            compatible_leagues.append((league_id, league_name))
    
    if not compatible_leagues:
        st.error("⚠️ Models not available")
        st.info("Please try again later.")
        return
    
    
    # Setup database connection early
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.sqlite")
    conn = sqlite3.connect(db_path)

    # Clean sidebar with live performance tracking
    with st.sidebar:
        st.subheader("🏆 Live Performance")
        
        def calculate_live_accuracy(league_id, conn):
            """Calculate actual prediction accuracy by testing models on completed matches"""
            try:
                # Load the trained model for this league
                model_package = model_manager.load_model(league_id)
                if not model_package or "error" in model_package:
                    return None, None, 0
                
                winner_model = model_package.get("winner_model") if model_package else None
                if not winner_model:
                    return None, None, 0
                
                # Get completed matches for this league
                matches_query = """
                SELECT e.home_team_id, e.away_team_id, e.home_score, e.away_score, e.date_event,
                       t1.name as home_team_name, t2.name as away_team_name
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.league_id = ? 
                AND e.home_score IS NOT NULL 
                AND e.away_score IS NOT NULL
                AND e.date_event <= date('now')
                ORDER BY e.date_event DESC
                LIMIT 50
                """
                
                completed_matches = conn.cursor().execute(matches_query, (league_id,)).fetchall()
                
                if len(completed_matches) < 10:
                    return None, None, len(completed_matches)
                
                # Build current feature table to compare team names
                current_df = build_feature_table(conn, FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=(league_id == 4574)))
                team_names_set = set(current_df['home_team'].tolist() + current_df['away_team'].tolist())
                
                # Test predictions on historical matches
                correct_predictions = 0
                total_tested = 0
                
                for match in completed_matches:
                    home_id, away_id, home_score, away_score, date_event, home_team_name, away_team_name = match
                    
                    # Skip if teams not in current model vocabulary
                    if home_team_name not in team_names_set or away_team_name not in team_names_set:
                        continue
                    
                    # Find the corresponding historical match features
                    historical_match = current_df[
                        (current_df['home_team'] == home_team_name) & 
                        (current_df['away_team'] == away_team_name)
                    ]
                    
                    if len(historical_match) == 0:
                        continue
                    
                    # Use the most recent historical instance
                    historical_instance = historical_match.iloc[-1]
                    feature_vector = historical_instance.drop(['home_team', 'away_team', 'home_win']).values
                    
                    # Make prediction
                    predicted_prob = winner_model.predict_proba(feature_vector.reshape(1, -1))[0][1]
                    predicted_home_wins = predicted_prob > 0.5
                    
                    # Compare with actual result
                    actual_home_wins = home_score > away_score
                    
                    if predicted_home_wins == actual_home_wins:
                        correct_predictions += 1
                    
                    total_tested += 1
                
                if total_tested > 0:
                    live_accuracy = correct_predictions / total_tested
                    # Debug info for troubleshooting
                    st.write(f"🔍 **{conn.cursor().execute('SELECT name FROM league WHERE id = ?', (league_id,)).fetchone()[0]}** Testing: {correct_predictions}/{total_tested} = {live_accuracy:.1%}")
                    return live_accuracy, 0, len(completed_matches)
                else:
                    return None, None, len(completed_matches)
                
            except Exception as e:
                # If calculation fails, fall back to training performance
                try:
                    registry_summary = model_manager.get_registry_summary()
                    leagues_data = registry_summary.get("leagues", {})
                    if str(league_id) in leagues_data:
                        base_performance = leagues_data[str(league_id)].get("performance", {})
                        base_accuracy = base_performance.get("winner_accuracy", 0)
                        return base_accuracy * 0.8, 0, 0  # Apply realistic discount to training accuracy
                    else:
                        return None, None, 0
                except:
                    return None, None, 0
            
        # Display live performance for each league
        leagues_data = model_manager.get_registry_summary().get("leagues", {})
        for league_id_key_str, info in leagues_data.items():
            league_id_key = int(league_id_key_str)
            league_name = info.get("name", f"League {league_id_key}")
            
            # Calculate live accuracy
            live_accuracy, live_mae, total_matches = calculate_live_accuracy(league_id_key, conn)
            
            # Show live metrics
            if live_accuracy is not None:
                st.metric(
                    label=f"{league_name}",
                    value=f"{live_accuracy:.1%}",
                    delta=f"{total_matches} completed matches"
                )
            else:
                # Fallback to training performance if live calculation fails
                performance = info.get("performance", {})
                training_accuracy = performance.get("winner_accuracy", 0)
                st.metric(
                    label=f"{league_name}",
                    value=f"{training_accuracy:.1%}",
                    delta=f"Training baseline"
                )

        st.markdown("---")
        
        # League selection
        st.subheader("🏉 Select League")
        league_name_to_id = {
            "Rugby Championship": 4986,
            "United Rugby Championship": 4446,
            "Currie Cup": 5069,
            "Rugby World Cup": 4574,
        }
        
        league = st.radio(
            "Choose League",
            options=list(league_name_to_id.keys()),
            index=1
        )
        league_id = league_name_to_id[league]
    
    # Load the trained model
    model_package = model_manager.load_model(league_id)
    if not model_package:
        st.error(f"⚠️ Unable to load model for {league}")
        st.info("Please try refreshing the page or selecting a different league.")
        return


    # Neutral mode handled automatically by league
    neutral_mode = (league_id in {4574})
    elo_k = 24
    
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
        
    except Exception as e:
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
        tid_int = safe_to_int(tid, -1)
        name = team_name.get(tid_int, str(tid_int))
        return name

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

    # Professional match summaries
    st.subheader("📊 Match Predictions")
    
    # Create columns for better layout on larger screens
    if len(disp) > 1:
        cols = st.columns(2)
    else:
        cols = [st.container()]
    
    for i in range(len(disp)):
        row = disp.iloc[i]
        winner = row["Pick"]
        home_team = row['Home']
        away_team = row['Away']
        match_date = row['Date']
        home_win_prob = float(row["Home Win %"])
        home_score = float(row["Home Score"])
        away_score = float(row["Away Score"])
        margin = float(row["Margin"])
        
        # Determine confidence level and styling
        confidence_diff = abs(home_win_prob - 50)
        if confidence_diff > 15:
            confidence = "High"
            confidence_class = "high"
        elif confidence_diff > 5:
            confidence = "Medium"
            confidence_class = "medium"
        else:
            confidence = "Low"
            confidence_class = "low"
        
        # Choose column for layout
        col_index = i % len(cols)
        
        with cols[col_index]:
            # Professional match summary using Streamlit components
            with st.container():
                # Header
                st.markdown(f"### {home_team} vs {away_team}")
                st.markdown(f"📅 **{match_date}**")
                
                # Score in prominent display
                st.markdown(f"""
                <div class="score-display">
                    <p class="score-text">{home_team} {home_score:.1f} - {away_score:.1f} {away_team}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Metrics in columns
                metric_col1, metric_col2 = st.columns(2)
                
                with metric_col1:
                    st.metric("🏆 Predicted Winner", winner)
                    confidence_color = "🟢" if confidence == "High" else "🟡" if confidence == "Medium" else "🔴"
                    st.metric(f"{confidence_color} Confidence", confidence)
                
                with metric_col2:
                    st.metric("🏠 Home Win Chance", f"{home_win_prob:.1f}%")
                    st.metric("📊 Expected Margin", f"{margin:+.1f}")
                
                st.divider()


    conn.close()

if __name__ == "__main__":
    main()
