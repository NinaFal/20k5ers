# Protection Layers - Anti-Regression System

Dit project heeft **4 lagen bescherming** tegen regressie van kritieke fixes:

## Layer 1: Code Comments
```python
# ============================================================================
# CRITICAL: DO NOT ADD CSV EXPORTS OR VALIDATION RUNS HERE!
# ============================================================================
```

## Layer 2: Docstrings
```python
def progress_callback(study, trial):
    """
    IMPORTANT: This function runs DURING optimization.
    - DO NOT run validation or final backtests here
    - DO NOT export CSV files here
    """
```

## Layer 3: Pre-Commit Checks
Bestand: `.github/pre-commit-checks.sh`

Controleert automatisch bij elke commit:
- ❌ Geen validation in progress_callback
- ❌ Geen export_trades_to_csv in main()
- ✅ archive_current_run() aanwezig
- ✅ Correcte imports (set_output_manager)

Run handmatig: `./github/pre-commit-checks.sh`

## Layer 4: Git Hook
Bestand: `.git/hooks/pre-commit`

Runt automatisch Layer 3 checks voor ELKE commit.
Als checks falen → commit wordt geblokkeerd.

## Layer 5: Documentation
- `.github/OPTIMIZATION_GUIDELINES.md` - Uitgebreide regels
- Deze README - Overzicht van alle lagen

## Kritieke Files (NIET aanpassen zonder checks)

1. **ftmo_challenge_analyzer.py**
   - `progress_callback()` - Alleen logging
   - `main()` - Gebruikt OutputManager
   - End of main() - Roept `archive_current_run()` aan

2. **tradr/utils/output_manager.py**
   - `save_best_trial_trades()` - Mode-specific exports
   - `archive_current_run()` - History backups

## Als Je Toch Wilt Veranderen

1. Lees eerst `.github/OPTIMIZATION_GUIDELINES.md`
2. Test lokaal met `./github/pre-commit-checks.sh`
3. Run test optimization: `python ftmo_challenge_analyzer.py --single --trials 2`
4. Verifieer files in `ftmo_analysis_output/TPE/` (niet root!)
5. Commit met duidelijke message waarom de change nodig was

## Restore Point

Laatste werkende versie:
- Commit: `1fae305` (2025-12-29)
- Tag: `v1.0-stable-optimization`

Terugzetten: `git checkout v1.0-stable-optimization`
