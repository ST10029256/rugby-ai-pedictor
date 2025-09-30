import pickle
import os

# Test the exact loading process step by step
legacy_path = 'artifacts/league_4574_model.pkl'
print('Step 1: Loading model...')

try:
    with open(legacy_path, 'rb') as f:
        model_data = pickle.load(f)
    print('OK Model loaded successfully')
    
    print('Step 2: Checking for gbdt_clf...')
    if 'models' in model_data and 'gbdt_clf' in model_data['models']:
        print('OK gbdt_clf found')
        
        print('Step 3: Accessing gbdt_clf...')
        gbdt_clf = model_data['models']['gbdt_clf']
        print(f'OK gbdt_clf type: {type(gbdt_clf)}')
        
        print('Step 4: Checking estimators...')
        if hasattr(gbdt_clf, 'estimators_'):
            print(f'OK Has {len(gbdt_clf.estimators_)} estimators')
            for i, est in enumerate(gbdt_clf.estimators_):
                print(f'  Estimator {i}: {type(est)}')
        
        print('Step 5: Testing copy...')
        simplified_model = model_data.copy()
        print('OK Copy successful')
        
        print('Step 6: Creating simplified models dict...')
        simplified_model['models'] = {
            'clf': model_data['models']['clf']
        }
        print('OK Simplified models dict created')
        
        print('Step 7: Setting model type...')
        simplified_model['model_type'] = 'simplified_legacy'
        print('OK Model type set')
        
        print('All steps completed successfully!')
        
except Exception as e:
    print(f'ERROR at step: {e}')
    import traceback
    traceback.print_exc()
