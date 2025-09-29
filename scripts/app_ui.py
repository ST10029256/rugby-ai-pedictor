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
try:
    from scripts.app_ui_optimized import main
    
    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"Error importing optimized app: {e}")
    print("Falling back to basic import...")
    exec(open(os.path.join(script_dir, 'app_ui_optimized.py')).read())

if __name__ == "__main__":
    # This file serves as a redirect to the optimized version
    # Streamlit Cloud will use this as the main entry point
    pass
