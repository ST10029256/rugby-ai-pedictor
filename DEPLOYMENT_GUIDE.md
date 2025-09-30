# Streamlit Cloud Deployment Guide

## Issue Resolution: Account Access Problem

The error "You don't have access to this app or it does not exist" occurs because there's a mismatch between your GitHub account and Streamlit Cloud account.

### Solution Options:

#### Option 1: Sign in with the correct GitHub account
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "Sign out" 
3. Sign in with the GitHub account that owns the repository (`st10029256`)
4. Your app should now be accessible

#### Option 2: Transfer the app to your current account
1. In Streamlit Cloud, go to your app settings
2. Look for "Transfer app" or "Change owner" option
3. Transfer the app to your current account (`dylanmiller424@gmail.com`)

#### Option 3: Create a new app with your current account
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Connect your GitHub repository
4. Set the main file to `expert_ai_app.py`
5. Deploy the app

## Deployment Configuration

### Required Files:
- ✅ `expert_ai_app.py` (main app file)
- ✅ `requirements.txt` (updated with compatible versions)
- ✅ `.streamlit/config.toml` (theme configuration)
- ✅ `secrets.toml.example` (template for secrets)

### Secrets Configuration:
For cloud deployment, you need to set up secrets in Streamlit Cloud:

1. Go to your app in Streamlit Cloud
2. Click "Settings" → "Secrets"
3. Add the following secrets:

```toml
SPORTDEVS_API_KEY = "your_actual_api_key_here"
```

### File Structure:
```
your-repo/
├── expert_ai_app.py          # Main app file
├── requirements.txt          # Dependencies
├── .streamlit/
│   ├── config.toml          # Streamlit configuration
│   └── secrets.toml         # Local secrets (not in git)
├── prediction/              # AI prediction modules
├── artifacts/               # Model files
├── artifacts_optimized/     # Optimized model files
└── data.sqlite             # Database file
```

## Troubleshooting

### Common Issues:

1. **Import Errors**: Make sure all Python files are in the correct directories
2. **Model Loading**: Ensure model files are committed to the repository
3. **Database Access**: SQLite files must be in the repository for cloud deployment
4. **API Keys**: Set up secrets properly in Streamlit Cloud

### Performance Notes:
- The app uses caching (`@st.cache_data`) for better performance
- Model files are loaded once and cached
- Database queries are optimized with caching

## Next Steps:
1. Resolve the account access issue using one of the options above
2. Verify all files are properly committed to your GitHub repository
3. Set up secrets in Streamlit Cloud
4. Redeploy the app if necessary

## Support:
If you continue to have issues, check the Streamlit Cloud documentation or contact Streamlit support.
