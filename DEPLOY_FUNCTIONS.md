# Deploy Firebase Cloud Functions

The Cloud Functions need to be manually deployed when `rugby-ai-predictor/main.py` changes.

## Deploy Command

From the project root, run:

```bash
firebase deploy --only functions
```

Or deploy just the get_league_metrics function:

```bash
firebase deploy --only functions:get_league_metrics
```

## Why Manual Deploy?

GitHub Actions workflows don't automatically deploy functions to avoid accidental deployments. Functions must be explicitly deployed when code changes.

## After Deployment

1. Wait 2-3 minutes for function deployment to complete
2. Check Firebase Console > Functions for deployment status
3. Test the app - it should now show XGBoost models

