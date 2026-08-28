#!/usr/bin/env python3
"""
$50.000 start, 2015-2025, elf jaar aaneen — nu MET echte cryptodata.

Dezelfde opzet als w5_50k_decade.py en dezelfde bevroren configuratie. Het enige
verschil is de data: BTC en ETH draaien nu op echte M15 vanaf augustus 2017,
XRP en ADA vanaf april/mei 2018, in plaats van uurbars vanaf 2023 voor alleen
BTC en ETH. Voor 2015 tot half 2017 verandert er niets, want zo ver terug
bestaat er geen cryptodata; het verschil begint in 2017 en wordt vanaf 2018
volledig.

Waarom apart en niet hervat in fiftyk_decade.json: die cache bevat jaren die op
de oude data zijn gemeten. Jaar 2015 hervatten en 2018 opnieuw draaien levert
een reeks op waarin de eerste helft uit een andere wereld komt dan de tweede,
en de doorgerolde balans draagt die vermenging het hele decennium mee. Dus
opnieuw vanaf 2015, in een eigen bestand, met het oude bestand ernaast om tegen
af te zetten.

De vergelijking is per jaar, niet alleen op het eindtotaal. Een gelijk eindbedrag
kan een heel ander pad hebben afgelegd, en het pad is wat bepaalt of een account
onderweg tegen een muur loopt.

Draaien:  uv run python3 backtest/src/w5_decade_crypto.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START_BALANCE = 50_000.0
YEARS = list(range(2015, 2026))
SCALE_CAP = "500000"
OUT = w5.W5_DIR / "decade_crypto.json"
OLD = w5.W5_DIR / "_pre_crypto" / "fiftyk_decade.json"


def run_year(year, balance):
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(b["env"])
    e["FIVEERS_MAX_SCALE"] = SCALE_CAP
    e["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"dec_{year}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{year}-01-01", "--end", f"{year}-12-31",
                        "--balance", f"{balance:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "geen results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        crypto = 0
        tc = d / "trades.csv"
        if tc.exists():
            import csv as _csv
            crypto = sum(1 for row in _csv.DictReader(open(tc))
                         if any(x in row["symbol"] for x in ("BTC", "ETH", "XRP", "ADA")))
        return {
            "start_balance": balance,
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "final_balance": r.get("final_balance"),
            "funded_level_end": (log[-1]["new_level"] if log else balance),
            "scale_ups": len(log),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"), "crypto_trades": crypto,
            "win_rate": r.get("win_rate"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    res = w5.load_json(OUT)
    years = res.setdefault("years", {})
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    bal = START_BALANCE
    for y in YEARS:
        if str(y) in years:
            bal = years[str(y)].get("funded_level_end") or bal
            continue
        if res.get("dead"):
            break
        print(f"[dec] {y}: start op ${bal:,.0f}", flush=True)
        r = run_year(y, bal)
        years[str(y)] = r
        w5.atomic_write(OUT, res)
        if r.get("error"):
            print(f"[dec] {y}: FOUT {r['error']}", flush=True); break
        cw = sum((v.get("withdrawn") or 0) for v in years.values())
        print(f"[dec] {y}: opgenomen ${r['withdrawn']:,.0f} (cum ${cw:,.0f})  "
              f"bal ${(r.get('final_balance') or 0):,.0f}  "
              f"lvl ${(r.get('funded_level_end') or 0):,.0f}  "
              f"trades {r['trades']} (crypto {r['crypto_trades']})  "
              f"DDD {r['max_ddd_pct']}%  TDD {r['max_tdd_pct']}%  win {r['win_rate']}%"
              + (f"   <-- DOOD: {r['fail_reason']}" if r.get("account_failed") else ""),
              flush=True)
        if r.get("account_failed"):
            res["dead"] = {"year": y, "reason": r.get("fail_reason")}
            w5.atomic_write(OUT, res); break
        bal = r.get("funded_level_end") or bal

    res["total_withdrawn"] = sum((v.get("withdrawn") or 0) for v in years.values())
    res["survived"] = not res.get("dead") and len(years) == len(YEARS)
    w5.atomic_write(OUT, res)

    old = json.loads(OLD.read_text()).get("scaled", {}).get("years", {}) if OLD.exists() else {}
    print("\n" + "=" * 96, flush=True)
    print("[dec] $50.000, 2015-2025, MET crypto  —  naast de oude meting ZONDER crypto", flush=True)
    print("=" * 96, flush=True)
    print(f"\n  {'jaar':<6}{'crypto':>8}{'opgenomen NIEUW':>18}{'opgenomen OUD':>16}"
          f"{'DDD n':>8}{'DDD o':>8}{'TDD n':>8}{'TDD o':>8}  {'niveau eind'}", flush=True)
    for y in YEARS:
        n = years.get(str(y)); o = old.get(str(y))
        if not n or n.get("error"):
            continue
        ov = f"${(o.get('withdrawn') or 0):,.0f}" if o else "-"
        od = f"{o.get('max_ddd_pct')}" if o else "-"
        ot = f"{o.get('max_tdd_pct')}" if o else "-"
        print(f"  {y:<6}{n['crypto_trades']:>8}${(n['withdrawn'] or 0):>17,.0f}{ov:>16}"
              f"{n['max_ddd_pct']:>8}{od:>8}{n['max_tdd_pct']:>8}{ot:>8}  "
              f"${(n.get('funded_level_end') or 0):,.0f}"
              + ("   DOOD" if n.get("account_failed") else ""), flush=True)

    ys = [v for v in years.values() if not v.get("error")]
    if ys:
        wd = max((v.get("max_ddd_pct") or 0) for v in ys)
        wt = max((v.get("max_tdd_pct") or 0) for v in ys)
        oy = [v for v in old.values() if not v.get("error")] if old else []
        owd = max((v.get("max_ddd_pct") or 0) for v in oy) if oy else None
        owt = max((v.get("max_tdd_pct") or 0) for v in oy) if oy else None
        ow = sum((v.get("withdrawn") or 0) for v in oy) if oy else None
        print(f"\n  {'':<26}{'NIEUW':>16}{'OUD':>16}", flush=True)
        print(f"  {'handelswinst':<26}${res['total_withdrawn']:>15,.0f}"
              + (f"${ow:>15,.0f}" if ow is not None else f"{'-':>16}"), flush=True)
        print(f"  {'slechtste dag (muur 5%)':<26}{wd:>15.2f}%"
              + (f"{owd:>15.2f}%" if owd is not None else f"{'-':>16}"), flush=True)
        print(f"  {'slechtste totaal (muur 10%)':<26}{wt:>15.2f}%"
              + (f"{owt:>15.2f}%" if owt is not None else f"{'-':>16}"), flush=True)
        print(f"  {'overleefd':<26}{str(res['survived']):>16}", flush=True)
        print(f"  {'cryptotrades totaal':<26}"
              f"{sum(v.get('crypto_trades') or 0 for v in ys):>16}", flush=True)
    print("\n[w5_decade_crypto] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
