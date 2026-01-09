#!/usr/bin/env python3
"""
Select optimization run for live trading.

This script allows manual selection of which optimization run to use
for live trading. The optimizer does NOT auto-save to current_params.json.

Usage:
    python scripts/select_run.py              # List available runs
    python scripts/select_run.py run009       # Select run009 for live trading
    python scripts/select_run.py --validate   # Validate current params

The selected run's parameters will be copied to params/current_params.json.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "ftmo_analysis_output"
PARAMS_DIR = PROJECT_ROOT / "params"
CURRENT_PARAMS = PARAMS_DIR / "current_params.json"
HISTORY_DIR = PARAMS_DIR / "history"


def find_runs() -> list[dict]:
    """Find all optimization runs with best_params.json."""
    runs = []
    
    # Search in all output subdirs (TPE, NSGA, TPE_H4, etc.)
    for subdir in OUTPUT_DIR.iterdir():
        if not subdir.is_dir():
            continue
        
        # Check for best_params.json directly in mode dir (latest run)
        direct_params = subdir / "best_params.json"
        if direct_params.exists():
            try:
                with open(direct_params) as f:
                    params = json.load(f)
                mtime = datetime.fromtimestamp(direct_params.stat().st_mtime)
                score = params.get("_metadata", {}).get("score", "N/A")
                runs.append({
                    "name": "latest",
                    "mode": subdir.name,
                    "path": subdir,
                    "params_file": direct_params,
                    "n_params": len([k for k in params if not k.startswith("_")]),
                    "modified": mtime,
                    "score": score,
                })
            except (json.JSONDecodeError, Exception) as e:
                print(f"⚠️  Error reading {direct_params}: {e}")
        
        # Look for history directory with run dirs
        history_dir = subdir / "history"
        if history_dir.exists() and history_dir.is_dir():
            for run_dir in history_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                if not run_dir.name.startswith(("run", "val")):
                    continue
                    
                params_file = run_dir / "best_params.json"
                if params_file.exists():
                    try:
                        with open(params_file) as f:
                            params = json.load(f)
                        
                        # Get modification time
                        mtime = datetime.fromtimestamp(params_file.stat().st_mtime)
                        
                        # Try to extract score from metadata or filename
                        score = params.get("_metadata", {}).get("score", "N/A")
                        
                        runs.append({
                            "name": run_dir.name,
                            "mode": subdir.name,
                            "path": run_dir,
                            "params_file": params_file,
                            "n_params": len([k for k in params if not k.startswith("_")]),
                            "modified": mtime,
                            "score": score,
                        })
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"⚠️  Error reading {params_file}: {e}")
    
    # Sort by modification time (newest first)
    runs.sort(key=lambda x: x["modified"], reverse=True)
    return runs


def list_runs() -> None:
    """List all available optimization runs."""
    runs = find_runs()
    
    if not runs:
        print("❌ No optimization runs found in ftmo_analysis_output/")
        print("   Run the optimizer first: python ftmo_challenge_analyzer.py")
        return
    
    print(f"\n📊 Available optimization runs ({len(runs)} found):\n")
    print(f"{'RUN':<10} {'MODE':<12} {'PARAMS':<8} {'MODIFIED':<20} {'SCORE':<15}")
    print("-" * 70)
    
    for run in runs:
        score_str = f"{run['score']:.4f}" if isinstance(run['score'], float) else str(run['score'])
        print(f"{run['name']:<10} {run['mode']:<12} {run['n_params']:<8} "
              f"{run['modified'].strftime('%Y-%m-%d %H:%M'):<20} {score_str:<15}")
    
    print("\n" + "-" * 70)
    print("Usage: python scripts/select_run.py <run_name>")
    print("Example: python scripts/select_run.py run009")
    
    # Show current params status
    print("\n📁 Current params status:")
    if CURRENT_PARAMS.exists():
        with open(CURRENT_PARAMS) as f:
            current = json.load(f)
        mtime = datetime.fromtimestamp(CURRENT_PARAMS.stat().st_mtime)
        n_params = len([k for k in current if not k.startswith("_")])
        source = current.get("_metadata", {}).get("source", "unknown")
        print(f"   ✅ current_params.json exists ({n_params} params)")
        print(f"   📅 Last modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        print(f"   📦 Source: {source}")
    else:
        print("   ⚠️  current_params.json does NOT exist!")
        print("   ❌ Live bot will FAIL without params!")


def select_run(run_name: str) -> bool:
    """Select a run for live trading by copying to current_params.json."""
    runs = find_runs()
    
    # Find the run
    matching = [r for r in runs if r["name"] == run_name]
    
    if not matching:
        print(f"❌ Run '{run_name}' not found!")
        print(f"   Available runs: {[r['name'] for r in runs]}")
        return False
    
    if len(matching) > 1:
        print(f"⚠️  Multiple runs named '{run_name}' found in different modes:")
        for r in matching:
            print(f"   - {r['mode']}/{r['name']}")
        print("   Using most recent one...")
    
    run = matching[0]  # Already sorted by date, newest first
    
    print(f"\n🎯 Selecting run: {run['mode']}/{run['name']}")
    print(f"   Source: {run['params_file']}")
    
    # Read source params
    with open(run["params_file"]) as f:
        params = json.load(f)
    
    # Add metadata
    params["_metadata"] = {
        "source": f"{run['mode']}/{run['name']}",
        "selected_at": datetime.now().isoformat(),
        "source_file": str(run['params_file']),
    }
    
    # Backup existing current_params.json
    if CURRENT_PARAMS.exists():
        HISTORY_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = HISTORY_DIR / f"current_params_backup_{timestamp}.json"
        shutil.copy(CURRENT_PARAMS, backup_path)
        print(f"   📦 Backed up existing params to: {backup_path.name}")
    
    # Write new params
    with open(CURRENT_PARAMS, "w") as f:
        json.dump(params, f, indent=2)
    
    n_params = len([k for k in params if not k.startswith("_")])
    print(f"\n✅ Copied {n_params} parameters to params/current_params.json")
    print(f"   Live bot will now use: {run['mode']}/{run['name']}")
    
    return True


def validate_params() -> bool:
    """Validate that current_params.json has all required parameters."""
    from params.defaults import PARAMETER_DEFAULTS, validate_params as do_validate
    
    if not CURRENT_PARAMS.exists():
        print("❌ current_params.json does NOT exist!")
        print("   Live bot will FAIL!")
        print("   Run: python scripts/select_run.py <run_name>")
        return False
    
    with open(CURRENT_PARAMS) as f:
        params = json.load(f)
    
    # Handle nested "parameters" format
    if "parameters" in params:
        params_clean = params["parameters"].copy()
    else:
        params_clean = {k: v for k, v in params.items() if not k.startswith("_")}
    
    # Remove metadata
    params_clean = {k: v for k, v in params_clean.items() if not k.startswith("_")}
    
    # Check for missing params
    missing = set(PARAMETER_DEFAULTS.keys()) - set(params_clean.keys())
    extra = set(params_clean.keys()) - set(PARAMETER_DEFAULTS.keys())
    
    print(f"\n🔍 Validating params/current_params.json:")
    print(f"   Parameters in file: {len(params_clean)}")
    print(f"   Parameters in defaults: {len(PARAMETER_DEFAULTS)}")
    
    if missing:
        print(f"\n❌ MISSING PARAMETERS ({len(missing)}):")
        for p in sorted(missing):
            print(f"   - {p}")
        print("\n   ⚠️  Live bot may fail or use wrong defaults!")
        return False
    
    if extra:
        print(f"\n⚠️  Extra parameters ({len(extra)}) - will be ignored:")
        for p in sorted(extra):
            print(f"   - {p}")
    
    print("\n✅ All required parameters present!")
    print("   Live bot is ready to run.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Select optimization run for live trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/select_run.py              # List available runs
  python scripts/select_run.py run009       # Select run009 for live trading
  python scripts/select_run.py --validate   # Validate current params
        """
    )
    parser.add_argument(
        "run_name",
        nargs="?",
        help="Name of the run to select (e.g., run009)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate current_params.json"
    )
    
    args = parser.parse_args()
    
    if args.validate:
        success = validate_params()
        sys.exit(0 if success else 1)
    elif args.run_name:
        success = select_run(args.run_name)
        sys.exit(0 if success else 1)
    else:
        list_runs()
        sys.exit(0)


if __name__ == "__main__":
    main()
