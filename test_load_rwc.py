import pickle

try:
    with open('artifacts_optimized/league_4574_model_optimized.pkl', 'rb') as f:
        model = pickle.load(f)
    print('Model loaded successfully in standalone script')
    print(f'League: {model["league_name"]}')
    print(f'Games trained: {model["training_games"]}')
    print(f'Model type: {model["model_type"]}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
