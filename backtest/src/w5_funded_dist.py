#!/usr/bin/env python3
"""
Foutmarges op het gefunde resultaat — punt 4 van de pre-mortem.

Het winstcijfer van dit project rust op EEN pad. Eén startdatum, één volgorde
van jaren, één uitkomst. De challenge heeft 196 metingen en dus een
betrouwbaarheidsinterval; het gefunde decennium heeft er één, en een enkele
trekking heeft geen spreiding. Dat is geen verwachtingswaarde, dat is een
bestaansbewijs.

Deze run trekt N onafhankelijke gefunde accounts, elk vanaf een eigen
willekeurige startdatum, elk drie jaar lang, elk vanaf $50.000 op de echte 5ers
ladder. Wat eruit komt is een VERDELING: hoe vaak overleeft het account drie
jaar, hoe vaak gaat het dood, en hoe breed ligt de winst.

WAT DIT WEL MEET
  overlevingskans van een gefund account over drie jaar
  spreiding van de opgenomen winst rond de mediaan
  het slechtste pad, niet alleen het gemiddelde

WAT DIT NIET MEET
  De vensters OVERLAPPEN in kalendertijd. 2018-2020 en 2019-2021 delen twee
  jaar en zijn dus niet onafhankelijk; de echte spreiding is breder dan deze
  steekproef suggereert. Elf jaar geschiedenis levert nu eenmaal geen twintig
  onafhankelijke drie-jaarsvensters op. Lees dit als "hoe gevoelig is de
  uitkomst voor waar je begint", niet als een zuiver betrouwbaarheidsinterval.

  En het is nog steeds dezelfde elf jaar waarop de configuratie is geoptimaliseerd.
  Een breder interval op in-sample data blijft in-sample.

Een breach beeindigt het account; de resterende jaren worden niet gedraaid.

Draaien:  uv run python3 backtest/src/w5_funded_dist.py [--runs 20] [--years 3]
"""
import argparse, concurrent.futures, importlib.util, json, os, random, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START_BALANCE = 50_000.0
SCALE_CAP = "500000"
SEED = 20260914
OUT = w5.W5_DIR / "funded_dist.json"
# Twee gelijktijdige accounts. De survival-optimizer draait op dezelfde vier
# kernen; drie zou hem uithongeren en die staat hoger op de lijst.
WORKERS = int(os.environ.get("W5_FD_WORKERS", "2"))


def fixed_bonus_for_level(level: float) -> int:
    if level >= 500_000:
        return 10_000
    if level >= 350_000:
        return 4_000
    return 0


def run_window(tag, start_iso, end_iso, balance):
    """Eén aaneengesloten venster op de 5ers-ladder, startend op `balance`."""
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(b["env"])
    e["FIVEERS_MAX_SCALE"] = SCALE_CAP
    e["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"fd_{tag}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", start_iso, "--end", end_iso,
                        "--balance", f"{balance:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=21600)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "geen results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        bonus = sum(fixed_bonus_for_level(ev.get("old_level") or 0) for ev in log)
        return {
            "start_balance": balance,
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "fixed_bonus": bonus,
            "final_balance": r.get("final_balance"),
            "funded_level_end": (log[-1]["new_level"] if log else balance),
            "scale_ups": len(log),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def one_account(start_iso, years):
    """Jaar voor jaar, zodat een herstart één jaar kost in plaats van drie."""
    from datetime import date
    s = date.fromisoformat(start_iso)
    store = w5.load_json(OUT)
    slot = store.setdefault(start_iso, {"years": {}})
    bal = START_BALANCE
    for i in range(years):
        a = s.replace(year=s.year + i).isoformat()
        bz = (s.replace(year=s.year + i + 1) - __import__("datetime").timedelta(days=1)).isoformat()
        key = str(i)
        # Elke lus opnieuw inlezen: parallelle accounts schrijven hetzelfde bestand.
        store = w5.load_json(OUT); slot = store.setdefault(start_iso, {"years": {}})
        if key in slot["years"]:
            r = slot["years"][key]
            if r.get("account_failed") or r.get("error"):
                return
            bal = r.get("funded_level_end") or bal
            continue
        r = run_window(f"{start_iso}_{i}", a, bz, bal)
        store = w5.load_json(OUT); slot = store.setdefault(start_iso, {"years": {}})
        slot["years"][key] = r
        slot["start"] = start_iso
        w5.atomic_write(OUT, store)
        if r.get("error"):
            print(f"[fd] {start_iso} jaar{i}: FOUT {r['error']}", flush=True); return
        print(f"[fd] {start_iso} jaar{i} {a}..{bz}: opgenomen ${r['withdrawn']:,.0f} "
              f"lvl ${(r.get('funded_level_end') or 0):,.0f} "
              f"DDD {r['max_ddd_pct']}% TDD {r['max_tdd_pct']}%"
              + (f"  <-- DOOD: {r['fail_reason']}" if r.get("account_failed") else ""),
              flush=True)
        if r.get("account_failed"):
            return
        bal = r.get("funded_level_end") or bal


def report(starts, years):
    store = w5.load_json(OUT)
    rows = []
    for s in starts:
        slot = store.get(s) or {}
        ys = [slot["years"][str(i)] for i in range(years) if str(i) in slot.get("years", {})]
        if not ys or any(y.get("error") for y in ys):
            continue
        died = any(y.get("account_failed") for y in ys)
        rows.append({
            "start": s,
            "jaren": len(ys),
            "dood": died,
            "opgenomen": sum((y.get("withdrawn") or 0) for y in ys),
            "bonus": sum((y.get("fixed_bonus") or 0) for y in ys),
            "eind": ys[-1].get("final_balance") or 0,
            "ergste_dag": max((y.get("max_ddd_pct") or 0) for y in ys),
            "ergste_totaal": max((y.get("max_tdd_pct") or 0) for y in ys),
        })
    if not rows:
        print("[fd] nog geen volledige accounts"); return
    rows.sort(key=lambda r: r["opgenomen"])
    print("\n" + "=" * 78)
    print(f"[fd] {len(rows)} gefunde accounts, elk {years} jaar vanaf $50.000")
    print(f"{'start':12} {'jaren':>5} {'opgenomen':>13} {'bonus':>9} "
          f"{'ergste dag':>11} {'ergste tot':>11}  uitkomst")
    for r in rows:
        print(f"{r['start']:12} {r['jaren']:>5} ${r['opgenomen']:>12,.0f} "
              f"${r['bonus']:>8,.0f} {r['ergste_dag']:>10.2f}% {r['ergste_totaal']:>10.2f}%  "
              + ("DOOD" if r["dood"] else "leeft"))
    tot = [r["opgenomen"] + r["bonus"] for r in rows]
    tot.sort()
    dood = sum(1 for r in rows if r["dood"])
    n = len(tot)
    def q(p):
        return tot[min(n - 1, int(p * n))]
    print(f"\n  dood        {dood}/{n}  ({100*dood/n:.0f}%)")
    print(f"  slechtste   ${tot[0]:,.0f}")
    print(f"  p25         ${q(0.25):,.0f}")
    print(f"  mediaan     ${tot[n//2]:,.0f}")
    print(f"  p75         ${q(0.75):,.0f}")
    print(f"  beste       ${tot[-1]:,.0f}")
    print(f"  ergste dag  {max(r['ergste_dag'] for r in rows):.2f}% / 5%")
    print(f"  ergste tot  {max(r['ergste_totaal'] for r in rows):.2f}% / 10%")
    print("\n[w5_funded_dist] DONE_MARKER", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    # Startdatums uit de canonieke lijst, maar alleen die waar nog `years` volle
    # jaren achter zitten. Dezelfde lijst als overal elders, zodat niemand later
    # kan zeggen dat dit op vriendelijker vensters is gemeten.
    last = 2026 - a.years
    pool = sorted(s for s in w5.CANON if int(s[:4]) <= last)
    rng = random.Random(SEED)
    starts = sorted(rng.sample(pool, min(a.runs, len(pool))))

    if a.report:
        report(starts, a.years); return

    print(f"[fd] {len(starts)} accounts x {a.years} jaar, {WORKERS} tegelijk", flush=True)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(lambda s: one_account(s, a.years), starts))
    report(starts, a.years)


if __name__ == "__main__":
    main()
