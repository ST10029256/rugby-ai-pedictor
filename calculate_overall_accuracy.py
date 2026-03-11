#!/usr/bin/env python3
import json

# Load model registry
with open('artifacts/model_registry.json', 'r') as f:
    data = json.load(f)

leagues = data['leagues']

# Calculate weighted averages
total_games = sum(l['training_games'] for l in leagues.values())
weighted_acc = sum(l['training_games'] * l['performance']['winner_accuracy'] for l in leagues.values()) / total_games
weighted_mae = sum(l['training_games'] * l['performance']['overall_mae'] for l in leagues.values()) / total_games

print("=" * 80)
print("OVERALL MODEL PERFORMANCE ACROSS ALL LEAGUES")
print("=" * 80)
print(f"\nTotal training games: {total_games:,}")
print(f"\n📊 WEIGHTED AVERAGE (by number of games):")
print(f"   Win/Lose Accuracy: {weighted_acc:.1%}")
print(f"   Margin Error (MAE): {weighted_mae:.2f} points")
print(f"\n   This means:")
print(f"   • {weighted_acc:.1%} of predictions correctly identify the winner")
print(f"   • On average, score predictions are off by {weighted_mae:.1f} points per team")
print(f"   • Total margin error: ~{weighted_mae * 2:.1f} points per game")

print(f"\n{'=' * 80}")
print("BREAKDOWN BY LEAGUE:")
print("=" * 80)
for league_id in sorted(leagues.keys()):
    l = leagues[league_id]
    acc = l['performance']['winner_accuracy']
    mae = l['performance']['overall_mae']
    games = l['training_games']
    print(f"\n{l['name']}:")
    print(f"   Accuracy: {acc:.1%} | MAE: {mae:.2f} points | Games: {games}")

