#!/usr/bin/env python3
"""Quick script to check Optuna study status and extract best trials."""

import sys
import os

# Add project root to path (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # Change to project root for database paths

import optuna
import json
from pathlib import Path

OPTUNA_DB_PATH = "sqlite:///regime_adaptive_v2_clean.db"
OPTUNA_STUDY_NAME = "regime_adaptive_v2_clean"

def main():
    try:
        study = optuna.load_study(
            study_name=OPTUNA_STUDY_NAME,
            storage=OPTUNA_DB_PATH
        )
    except Exception as e:
        print(f"Error loading study: {e}")
        return
    
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    
    print(f"\n{'='*60}")
    print("OPTUNA STUDY STATUS")
    print(f"{'='*60}")
    print(f"Total Trials: {len(study.trials)}")
    print(f"Completed Trials: {len(completed)}")
    
    if completed:
        # Sort by value (descending)
        sorted_trials = sorted(completed, key=lambda t: t.value if t.value else 0, reverse=True)
        
        print(f"\nBest Score: {study.best_value:.2f}")
        print(f"Best Trial: #{study.best_trial.number}")
        
        print(f"\n{'='*60}")
        print("TOP 5 TRIALS")
        print(f"{'='*60}")
        
        for i, trial in enumerate(sorted_trials[:5]):
            print(f"\n#{i+1} - Trial {trial.number}")
            print(f"   Score: {trial.value:.2f}")
            print(f"   Sharpe: {trial.user_attrs.get('sharpe_ratio', 'N/A')}")
            print(f"   Win Rate: {trial.user_attrs.get('win_rate', 'N/A')}%")
            print(f"   Total R: {trial.user_attrs.get('total_r', 'N/A')}")
            print(f"   Max DD: {trial.user_attrs.get('max_drawdown_pct', 'N/A')}%")
            print("   Parameters:")
            for k, v in sorted(trial.params.items()):
                if isinstance(v, float):
                    print(f"     {k}: {v:.3f}")
                else:
                    print(f"     {k}: {v}")
        
        # Save best params
        best_params = study.best_params
        print(f"\n{'='*60}")
        print("BEST PARAMETERS (saved to best_params.json)")
        print(f"{'='*60}")
        
        params_to_save = {
            'min_confluence_score': best_params.get('min_confluence_score', 3),
            'min_quality_factors': best_params.get('min_quality_factors', 2),
            'risk_per_trade_pct': best_params.get('risk_per_trade_pct', 0.5),
            'atr_min_percentile': best_params.get('atr_min_percentile', 60.0),
            'trail_activation_r': best_params.get('trail_activation_r', 2.2),
            'volatile_asset_boost': best_params.get('volatile_asset_boost', 1.0),
            'adx_trend_threshold': best_params.get('adx_trend_threshold', 25),
            'adx_range_threshold': best_params.get('adx_range_threshold', 20),
            'trend_min_confluence': best_params.get('trend_min_confluence', 6),
            'range_min_confluence': best_params.get('range_min_confluence', 5),
            'atr_vol_ratio_range': best_params.get('atr_vol_ratio_range', 1.0),
            'atr_trail_multiplier': best_params.get('atr_trail_multiplier', 1.5),
            'partial_exit_at_1r': best_params.get('partial_exit_at_1r', True),
            'partial_exit_pct': best_params.get('partial_exit_pct', 0.5),
        }
        
        for k, v in sorted(params_to_save.items()):
            if isinstance(v, float):
                print(f"  {k}: {v:.3f}")
            else:
                print(f"  {k}: {v}")
        
        # Save to file
        Path("best_params.json").write_text(json.dumps(params_to_save, indent=2))
        print(f"\n✅ Best parameters saved to best_params.json")
        
    else:
        print("No completed trials found")

if __name__ == "__main__":
    main()
