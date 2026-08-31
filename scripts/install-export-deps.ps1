# Install deps for export_pre_kickoff_replay_excel.py on Windows / Python 3.13+
# NEVER use: pip install -r requirements.txt  (sklearn 1.3.2 will try to compile and fail)

$ErrorActionPreference = "Stop"

Write-Host "Installing export script dependencies (pre-built wheels only for sklearn)..." -ForegroundColor Cyan

pip install --upgrade pip

# Force wheel for sklearn — do not compile from source
pip install --only-binary scikit-learn "scikit-learn>=1.5.0"

pip install "pandas>=2.0.0,<2.3.0" "openpyxl>=3.1.0" "numpy>=1.24.0,<2.0.0" "joblib>=1.3.0" "requests>=2.32.0"

# torch: use CPU wheel index if default install is slow
pip install torch

python -c "import pandas, openpyxl, numpy, sklearn, torch; print('OK: pandas', pandas.__version__, 'sklearn', sklearn.__version__, 'torch', torch.__version__)"

Write-Host ""
Write-Host "Done. Run:" -ForegroundColor Green
Write-Host "  python scripts/export_pre_kickoff_replay_excel.py --db data.sqlite --output pre_kickoff_replay_export.xlsx"
