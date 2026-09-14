#!/usr/bin/env python3
"""
Bevestiging van een survival-kandidaat — de stap die van een kandidaat een
vervanger maakt, of hem afschiet.

WAAROM DIT MOET. w5_survival.py kiest de beste van tachtig trials op DERTIG
gedeelde vensters, en die dertig zijn bovendien CASE-ENRICHED: alle zeven
vensters waarop de baseline breacht zitten er per constructie in. Dat is precies
de opzet waarin de winnaar er beter uitziet dan hij is. Dezelfde fout staat aan
het begin van dit project: de vorige baseline scoorde 0 breaches op 25 vensters
en daarna 7 op 100.

De breach-TELLING uit de screen is geen breach-PERCENTAGE. Hij is opgeblazen en
mag nooit als percentage worden geciteerd.

TWEE TRAPPEN, in deze volgorde, want de eerste is half zo duur als de tweede.

  HOLDOUT  De 70 overgebleven vensters uit HOLDOUT_100_STARTS_2015.json — 33 uit
           2019+ en 37 van ervoor. De baseline OVERLEEFT ze allemaal. Deze trap
           vangt dus de kandidaat die de zeven bekende mislukkingen inruilt voor
           NIEUWE. Zakt hij hier, dan is hij overfit en houdt het op.

  FRESH    CONFIRM_100_STARTS.json, seed 20260810, disjunct van elke andere
           lijst in dit project. Dit levert het enige onvertekende getal.

GEPAARD, en dat is het hele punt. Beide armen draaien op DEZELFDE vensters, dus
het verschil is per venster te lezen en de steekproefruis valt grotendeels tegen
zichzelf weg. Met een handvol breaches op 70 vensters is dat het verschil tussen
een meting en een gok. De toets is McNemar op de gepaarde breach-tabel: alleen
de vensters waar de armen VAN ELKAAR VERSCHILLEN dragen bij, want de rest zegt
niets over welke arm beter is.

DE OUDE HOLDOUT IS HIER NIET BRUIKBAAR als referentie. holdout100.json dateert
van voor de symboolwijzigingen (crypto eruit, goud en zilver eruit, CAD_JPY
eruit, olie erbij, UK100 terug). De incumbent wordt daarom opnieuw gemeten,
niet uit dat bestand gelezen.

GEEN VROEGTIJDIGE AFBREKING. Elke start loopt af, zodat het aantal breaches het
echte aantal is en niet afgekapt bij de eerste.

Draaien:
    uv run python3 backtest/src/w5_confirm_candidate.py --trial 31
    uv run python3 backtest/src/w5_confirm_candidate.py --trial 31 --stage fresh
    uv run python3 backtest/src/w5_confirm_candidate.py --trial 31 --report
"""
import argparse, concurrent.futures, csv as _csv, importlib.util, json, math, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

TRIALS_CSV = w5.W5_DIR / "survival_trials.csv"
SPLIT = w5.W5_DIR / "survival_split.json"
OUT = w5.W5_DIR / "confirm_candidate.json"

# De kolomnaam in survival_trials.csv -> waar hij heen moet.
ENV_KEYS = {
    "cum_risk": "CFG_MAX_CUM_RISK", "max_pos": "MAX_TOTAL_POSITIONS",
    "corr_cap": "CORR_GROUP_CAP", "tdd_caution": "CFG_TDD_CAUTION_PCT",
    "risk_cautious": "CFG_RISK_CAUTIOUS", "wall_safety": "TDD_WALL_SAFETY",
    "nightly_reduce": "NIGHTLY_REDUCE_PCT", "nightly_close_r": "NIGHTLY_R_CLOSE_LOSING",
}
TP_KEYS = {"risk_per_trade_pct": "risk_per_trade_pct"}


def frozen():
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    return env, tp


def candidate(trial_no):
    rows = list(_csv.DictReader(open(TRIALS_CSV)))
    hit = [r for r in rows if r["trial"] == str(trial_no)]
    if not hit:
        raise SystemExit(f"trial {trial_no} staat niet in {TRIALS_CSV.name}")
    r = hit[0]
    env, tp = frozen()
    for col, key in ENV_KEYS.items():
        env[key] = str(r[col])
    for col, key in TP_KEYS.items():
        tp[key] = float(r[col])
    return env, tp, r


def starts_for(stage):
    if stage == "holdout":
        return json.loads(SPLIT.read_text())["holdout"]
    return json.loads((w5.DOE_DIR / "CONFIRM_100_STARTS.json").read_text())["starts"]


def run_arm(name, env, tp, starts, stage):
    """Volledig, zonder afbreken. Gecached per (arm, stage, start)."""
    store = w5.load_json(OUT)
    slot = store.setdefault(stage, {}).setdefault(name, {})
    todo = [s for s in starts if s not in slot]
    if todo:
        print(f"[bevestig] {stage}/{name}: {len(todo)} te gaan", flush=True)
    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            done = {}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                done[futs[f]] = r
            store = w5.load_json(OUT)
            slot = store.setdefault(stage, {}).setdefault(name, {})
            slot.update(done)
            w5.atomic_write(OUT, store)
            br = sum(1 for v in slot.values() if v.get("breach"))
            print(f"[bevestig] {stage}/{name} {len(slot)}/{len(starts)} breach={br}", flush=True)
    return w5.load_json(OUT).get(stage, {}).get(name, {})


def summarise(d, starts):
    rows = [d[s] for s in starts if s in d]
    br = sum(1 for r in rows if r.get("breach"))
    tot = sorted(r["total"] for r in rows if r.get("total") is not None)
    return {"n": len(rows), "pass": len(tot), "breach": br,
            "stall": len(rows) - br - len(tot),
            "median": tot[len(tot) // 2] if tot else None,
            "le30": sum(1 for t in tot if t <= 30)}


def mcnemar_exact(b, c):
    """Tweezijdige exacte tekentoets op de discordante paren.

    b = vensters waar ALLEEN de incumbent breacht, c = alleen de kandidaat.
    De concordante paren dragen niet bij: ze zeggen niets over welke arm beter
    is. Met b+c klein is de normale benadering waardeloos, dus exact.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def report(stage, starts, cand_row=None):
    store = w5.load_json(OUT).get(stage, {})
    inc, can = store.get("incumbent", {}), store.get("candidate", {})
    shared = [s for s in starts if s in inc and s in can]
    if not shared:
        print(f"[bevestig] {stage}: nog niets te melden"); return
    si, sc = summarise(inc, shared), summarise(can, shared)
    print("\n" + "=" * 70)
    print(f"TRAP {stage.upper()} — {len(shared)} gepaarde vensters")
    if cand_row:
        print(f"kandidaat = trial {cand_row['trial']}: risk {cand_row['risk_per_trade_pct']}% "
              f"muurmarge {cand_row['wall_safety']} voorzichtig vanaf {cand_row['tdd_caution']}%")
    print(f"\n{'':14}{'incumbent':>12}{'kandidaat':>12}")
    for lbl, k in (("geslaagd", "pass"), ("breach", "breach"), ("vastgelopen", "stall"),
                   ("<=30 dagen", "le30"), ("mediaan (d)", "median")):
        print(f"{lbl:14}{str(si[k]):>12}{str(sc[k]):>12}")
    b = sum(1 for s in shared if inc[s].get("breach") and not can[s].get("breach"))
    c = sum(1 for s in shared if can[s].get("breach") and not inc[s].get("breach"))
    both = sum(1 for s in shared if can[s].get("breach") and inc[s].get("breach"))
    p = mcnemar_exact(b, c)
    print(f"\ngepaarde breach-tabel: beide {both} | alleen incumbent {b} | alleen kandidaat {c}")
    print(f"McNemar exact, tweezijdig: p = {p:.3f}")
    if c:
        print("\nNIEUWE breaches van de kandidaat (vensters die de incumbent overleeft):")
        for s in shared:
            if can[s].get("breach") and not inc[s].get("breach"):
                print(f"  {s}")
    print("\n[w5_confirm_candidate] DONE_MARKER", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--stage", choices=("holdout", "fresh"), default="holdout")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    env_c, tp_c, row = candidate(a.trial)
    starts = starts_for(a.stage)
    if a.report:
        report(a.stage, starts, row); return

    env_i, tp_i = frozen()
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    print(f"[bevestig] trap {a.stage}, {len(starts)} vensters, trial {a.trial}", flush=True)
    run_arm("incumbent", env_i, tp_i, starts, a.stage)
    run_arm("candidate", env_c, tp_c, starts, a.stage)
    report(a.stage, starts, row)


if __name__ == "__main__":
    main()
