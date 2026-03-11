# Expected XGBoost Model Accuracies (Deployed Firebase App)

Based on full evaluation of 1,871 completed games across all leagues.

## Expected Accuracies by League

| League ID | League Name | XGBoost Accuracy | Games Tested |
|-----------|-------------|------------------|--------------|
| **4414** | English Premiership Rugby | **77.88%** | 208 games |
| **4430** | French Top 14 | **81.23%** | 325 games |
| **4446** | United Rugby Championship | **79.94%** | 344 games |
| **4551** | Super Rugby | **76.06%** | 259 games |
| **4574** | Rugby World Cup | **92.76%** | 152 games |
| **4986** | Rugby Championship | **56.25%** | 144 games |
| **5069** | Currie Cup | **71.59%** | 345 games |
| **5479** | Rugby Union International Friendlies | **89.36%** | 94 games |

## Overall Expected Performance

- **Overall XGBoost Accuracy**: **77.55%** (1451/1871 games)
- **Overall XGBoost MAE**: **6.32 points** (Mean Absolute Error for score predictions)

## How to Verify XGBoost is Deployed

1. **Check League Metrics API**: 
   - Call `get_league_metrics` Cloud Function for each league
   - Verify `model_type` field shows `"xgboost"`
   - Verify accuracy percentages match (within ±2% due to ongoing retraining)

2. **Expected Accuracy Ranges** (accounting for model updates):
   - English Premiership: ~76-80%
   - French Top 14: ~79-83%
   - United Rugby Championship: ~78-82%
   - Super Rugby: ~74-78%
   - Rugby World Cup: ~90-95%
   - Rugby Championship: ~54-58%
   - Currie Cup: ~70-73%
   - International Friendlies: ~87-91%

3. **If seeing Optimized/Stacking accuracies instead:**
   - Optimized would show: 78.67% overall (vs XGBoost 77.55%)
   - This would indicate the wrong model type is loaded

## Expected Optimized (Stacking) Model Accuracies

| League ID | League Name | Optimized Accuracy | Games Tested |
|-----------|-------------|-------------------|--------------|
| **4414** | English Premiership Rugby | **83.17%** | 208 games |
| **4430** | French Top 14 | **82.77%** | 325 games |
| **4446** | United Rugby Championship | **82.85%** | 344 games |
| **4551** | Super Rugby | **77.61%** | 259 games |
| **4574** | Rugby World Cup | **91.45%** | 152 games |
| **4986** | Rugby Championship | **49.31%** | 144 games |
| **5069** | Currie Cup | **71.01%** | 345 games |
| **5479** | Rugby Union International Friendlies | **94.68%** | 94 games |

**Overall Optimized Accuracy**: **78.67%** (1472/1871 games)

## Side-by-Side Comparison: XGBoost vs Optimized

| League ID | League Name | XGBoost | Optimized | Winner |
|-----------|-------------|---------|-----------|--------|
| 4414 | English Premiership | 77.88% | **83.17%** | Optimized +5.29% |
| 4430 | French Top 14 | 81.23% | **82.77%** | Optimized +1.54% |
| 4446 | United Rugby Championship | 79.94% | **82.85%** | Optimized +2.91% |
| 4551 | Super Rugby | 76.06% | **77.61%** | Optimized +1.54% |
| 4574 | Rugby World Cup | **92.76%** | 91.45% | XGBoost +1.32% |
| 4986 | Rugby Championship | **56.25%** | 49.31% | XGBoost +6.94% |
| 5069 | Currie Cup | **71.59%** | 71.01% | XGBoost +0.58% |
| 5479 | International Friendlies | 89.36% | **94.68%** | Optimized +5.32% |

## Key Differences: XGBoost vs Optimized

| Metric | XGBoost | Optimized Stacking | Winner |
|--------|---------|-------------------|--------|
| **Overall Winner Accuracy** | 77.55% | **78.67%** | Optimized +1.12% |
| **Overall Score MAE** | **6.32** | 7.42 | XGBoost (1.09 points better) |
| **Model Type** | `xgboost` | `stacking` | - |

### Summary:
- **Winner Prediction**: Optimized is slightly better (+1.12% overall)
- **Score Prediction**: XGBoost is significantly better (1.09 points lower MAE)
- **League Performance**: Optimized wins in 5 leagues, XGBoost wins in 3 leagues

**Note**: If your deployed app shows Optimized accuracies, it's loading the wrong models from `artifacts_optimized/` instead of `artifacts/`. Check the `model_type` field in `get_league_metrics` - it should be `"xgboost"` not `"stacking"`.

