#!/usr/bin/env python3
"""
Willekeurige startdatums, met de configuratie die LIVE draait.

Twee vragen, elk met een verdeling in plaats van één pad:

  challenges   N willekeurige 2-staps challenges (8% dan 5%, 5% dagmuur, 10%
               totaalmuur, regel van 3 winstdagen). Hoe vaak slaagt het, hoe
               vaak breach, hoe lang duurt het.
  funded       N gefunde accounts per lengte (3, 5, 8 jaar), elk AAN EEN STUK
               gedraaid vanaf een willekeurige startdatum en $50.000 op de echte
               5ers-ladder. Hoe vaak overleeft het, hoeveel wordt er opgenomen.

WAT DRAAIT: BASELINE_t65_tdd_FROZEN (w5_acceptance bewijst dat live daarop
staat), plus wat live sindsdien ook doet: realistische kosten (spreadkaart
begrensd op het eigen filter van 3,0 pip) en de pin-bewaking (PEG_GUARD_VOL=2.5,
live standaard aan).

WAT DIT NIET IS. Dezelfde elf jaar waarop de configuratie is afgesteld, en de
vensters overlappen (een 8-jaarsvenster kan alleen starten tussen 2015 en 2017).
De spreiding die hieruit komt is een ondergrens van de echte spreiding.

Draaien:  uv run python3 backtest/src/w5_random_study.py challenges [--n 100]
          uv run python3 backtest/src/w5_random_study.py funded --years 3 [--n 20]
          uv run python3 backtest/src/w5_random_study.py report
"""
import argparse, concurrent.futures, importlib.util, json, os, random, shutil, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)
_cr = importlib.util.spec_from_file_location("cr", str(HERE / "w5_costs_real.py"))
cr = importlib.util.module_from_spec(_cr); _cr.loader.exec_module(cr)

OUT = w5.W5_DIR / "random_study.json"
WORKERS = int(os.environ.get("W5_RS_WORKERS", "3"))
DATA_FIRST, DATA_LAST = date(2015, 1, 2), date(2025, 12, 31)
SEED = 20260925
START_BALANCE = 50_000.0


def live_config():
    """Frozen baseline + live additions (costs, peg guard)."""
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    env["SLIPPAGE_MAP"] = json.dumps(cr.spread_map_real(1.0))
    env["COST_LIMIT_ENTRIES"] = "1"
    env["PEG_GUARD_VOL"] = "2.5"
    env["CFG_DAILY_WALL_PCT"] = "5.0"
    return env, tp


def draw(n, lo, hi, seed):
    rng = random.Random(seed)
    span = (hi - lo).days
    out = set()
    while len(out) < n:
        d = lo + timedelta(days=rng.randrange(span + 1))
        if d.weekday() < 5:
            out.add(d.isoformat())
    return sorted(out)


def shift_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


# ── challenges ───────────────────────────────────────────────────────────────
def challenge_starts(n):
    # Twee stappen van elk tot HORIZON dagen moeten binnen de data passen.
    return draw(n, DATA_FIRST, DATA_LAST - timedelta(days=2 * w5.HORIZON + 5), SEED)


def run_challenges(n):
    env, tp = live_config()
    starts = challenge_starts(n)
    store = w5.load_json(OUT)
    todo = [s for s in starts if s not in store.get("challenges", {})]
    print(f"[rs] challenges: {len(todo)} van {len(starts)} te gaan", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s for s in todo}
        for f in concurrent.futures.as_completed(futs):
            s = futs[f]
            try:
                r = f.result(); r.pop("detail", None)
            except Exception as e:
                r = {"start": s, "error": repr(e)}
            store = w5.load_json(OUT)
            store.setdefault("challenges", {})[s] = r
            w5.atomic_write(OUT, store)
            done = store["challenges"]
            print(f"[rs] {s}: {'BREACH ' + r.get('why','') if r.get('breach') else ('geslaagd in ' + str(r.get('total')) + 'd' if r.get('total') else 'niet binnen horizon')}"
                  f"   ({len(done)}/{len(starts)})", flush=True)


# ── funded, aan een stuk ─────────────────────────────────────────────────────
def funded_starts(years, n):
    last = date(DATA_LAST.year - years, DATA_LAST.month, DATA_LAST.day)
    return draw(n, DATA_FIRST, last, SEED + years)


def run_funded_one(years, start_iso):
    env, tp = live_config()
    s = date.fromisoformat(start_iso)
    end = (shift_years(s, years) - timedelta(days=1)).isoformat()
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(env)
    e["FIVEERS_MAX_SCALE"] = "500000"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"rs_{years}y_{start_iso}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST), "--start", start_iso,
                        "--end", end, "--balance", f"{START_BALANCE:.2f}", "--output", str(d),
                        "--quiet"], env=e, cwd=str(w5.cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=6 * 3600)
        rj = d / "results.json"
        if not rj.exists():
            return {"start": start_iso, "error": "geen results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        fi = r.get("fail_info") or {}
        return {"start": start_iso, "end": end,
                "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
                "final_balance": r.get("final_balance"),
                "level_end": (log[-1]["new_level"] if log else START_BALANCE),
                "scale_ups": len(log),
                "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "died": bool(r.get("account_failed")),
                "death_time": fi.get("time"), "death_reason": fi.get("reason")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_funded(years, n):
    starts = funded_starts(years, n)
    key = f"funded_{years}y"
    store = w5.load_json(OUT)
    todo = [s for s in starts if s not in store.get(key, {}) or store[key][s].get("error")]
    print(f"[rs] {key}: {len(todo)} van {len(starts)} te gaan", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(run_funded_one, years, s): s for s in todo}
        for f in concurrent.futures.as_completed(futs):
            r = f.result()
            store = w5.load_json(OUT)
            store.setdefault(key, {})[futs[f]] = r
            w5.atomic_write(OUT, store)
            print(f"[rs] {key} {futs[f]}: "
                  + (f"FOUT {r['error']}" if r.get("error") else
                     f"opgenomen ${r['withdrawn']:,.0f}  DDD {r['max_ddd_pct']}%  TDD {r['max_tdd_pct']}%"
                     + (f"  <-- DOOD {r['death_time']} {r['death_reason']}" if r['died'] else "")),
                  flush=True)


# ── rapport ──────────────────────────────────────────────────────────────────
def q(vals, p):
    return vals[min(len(vals) - 1, int(p * len(vals)))] if vals else None


def report():
    store = w5.load_json(OUT)
    ch = [r for r in store.get("challenges", {}).values() if not r.get("error")]
    if ch:
        n = len(ch)
        tot = sorted(r["total"] for r in ch if r.get("total") is not None)
        br = [r for r in ch if r.get("breach")]
        stall = n - len(tot) - len(br)
        print(f"\nCHALLENGES ({n})")
        print(f"  geslaagd     {len(tot)}/{n} ({100*len(tot)/n:.0f}%)")
        print(f"  breach       {len(br)}/{n} ({100*len(br)/n:.0f}%)  "
              f"stap1 {sum(1 for r in br if r.get('why')=='step1')}, stap2 {sum(1 for r in br if r.get('why')=='step2')}")
        print(f"  niet binnen  {stall}/{n}  ({w5.HORIZON} dagen per stap)")
        if tot:
            print(f"  dagen tot geslaagd: p10 {q(tot,.1)}  mediaan {tot[len(tot)//2]}  p90 {q(tot,.9)}  max {tot[-1]}")
            print(f"  binnen 30 dagen {sum(1 for t in tot if t<=30)}/{n}, binnen 60 {sum(1 for t in tot if t<=60)}/{n}")
        for r in sorted(br, key=lambda r: r["start"]):
            print(f"    breach {r['start']} ({r.get('why')})")
    for y in (3, 5, 8):
        rows = [r for r in store.get(f"funded_{y}y", {}).values() if not r.get("error")]
        if not rows:
            continue
        n = len(rows)
        died = [r for r in rows if r["died"]]
        w = sorted(r["withdrawn"] for r in rows)
        print(f"\nGEFUND {y} JAAR AAN EEN STUK ({n} accounts vanaf $50.000)")
        print(f"  overleeft    {n-len(died)}/{n} ({100*(n-len(died))/n:.0f}%)")
        print(f"  opgenomen    slechtste ${w[0]:,.0f}  p25 ${q(w,.25):,.0f}  mediaan ${w[n//2]:,.0f}  "
              f"p75 ${q(w,.75):,.0f}  beste ${w[-1]:,.0f}")
        print(f"  ergste dag   {max(r['max_ddd_pct'] or 0 for r in rows):.2f}% / 5%   "
              f"ergste totaal {max(r['max_tdd_pct'] or 0 for r in rows):.2f}% / 10%")
        for r in sorted(died, key=lambda r: r["start"]):
            print(f"    DOOD start {r['start']}: {r['death_time']} {r['death_reason']}  (opgenomen ${r['withdrawn']:,.0f})")
    print("\n[w5_random_study] DONE_MARKER", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["challenges", "funded", "report"])
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--years", type=int, default=3)
    a = ap.parse_args()
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    if a.mode == "challenges":
        run_challenges(a.n or 100)
    elif a.mode == "funded":
        run_funded(a.years, a.n or 20)
    report()
