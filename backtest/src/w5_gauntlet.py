#!/usr/bin/env python3
"""
The between-stage filter: run a stage's top 20 across 2016-2025 and keep only
configs with ZERO breaches.

Each year runs as a fresh $100k funded account (scaling capped at $175k). Two
reasons for per-year rather than one continuous decade:

  * a single 10-year subprocess cannot survive this container's restart cadence,
    and it caches nothing on the way — a kill loses hours;
  * fresh-$100k years make the years directly comparable, which is what "no
    breaches anywhere" should mean.

Caveat stated plainly: chunking resets the TOTAL-drawdown baseline each January,
so this arm UNDER-detects slow multi-year 10%-wall bleeds. Daily-wall detection
is exact (measured within a day), and the daily wall is the constraint this
round is optimizing against.

Survivors are ranked on the funded-account criteria the user asked for — total
payout, win rate — and the best is written to wall5/current_best.json for the
next stage to build on.

Run:  uv run python3 backtest/src/w5_gauntlet.py --stage ladder
"""
import argparse, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    st = args.stage
    top_path = w5.W5_DIR / f"{st}_top20.json"
    if not top_path.exists():
        print(f"[gauntlet:{st}] {top_path.name} not found — run the stage first", flush=True)
        return
    cands = json.loads(top_path.read_text())[:args.top]
    res_path = w5.W5_DIR / f"{st}_gauntlet.json"
    res = w5.load_json(res_path)

    print(f"[gauntlet:{st}] {len(cands)} configs x {len(w5.DECADE_YEARS)} years, "
          f"fresh $100k each year, 5% wall", flush=True)

    for c in cands:
        key = str(c["trial"])
        slot = res.setdefault(key, {"env": c["env"], "tp": c["tp"], "years": {}})
        env = dict(w5.BASE_ENV); env.update(c["env"])
        tp = dict(w5.BASE_TP); tp.update(c["tp"])
        for y in w5.DECADE_YEARS:
            if str(y) in slot["years"]:
                continue
            if any(v.get("account_failed") for v in slot["years"].values()):
                break                      # already disqualified — stop paying for it
            slot["years"][str(y)] = w5.decade_run(env, tp, y)
            w5.atomic_write(res_path, res)
        yrs = slot["years"]
        failed = [y for y, v in yrs.items() if v.get("account_failed")]
        slot["breach_years"] = failed
        slot["clean"] = (len(yrs) == len(w5.DECADE_YEARS)) and not failed
        w5.atomic_write(res_path, res)
        tag = "CLEAN" if slot["clean"] else (f"FAILED {failed}" if failed else "incomplete")
        print(f"  trial {key:>4}: {len(yrs)}/{len(w5.DECADE_YEARS)} years  {tag}", flush=True)

    # rank survivors on the funded-account criteria: payout, then win rate
    clean = []
    for k, v in res.items():
        if not v.get("clean"):
            continue
        yrs = list(v["years"].values())
        pay = sum((y.get("withdrawn") or 0) for y in yrs)
        net = sum((y.get("net_pnl") or 0) for y in yrs)
        wr = [y.get("win_rate") for y in yrs if y.get("win_rate") is not None]
        ddd = max((y.get("max_ddd_pct") or 0) for y in yrs)
        tdd = max((y.get("max_tdd_pct") or 0) for y in yrs)
        clean.append({"trial": k, "payout": pay, "net": net,
                      "win_rate": round(sum(wr) / len(wr), 1) if wr else None,
                      "worst_ddd": ddd, "worst_tdd": tdd,
                      "env": v["env"], "tp": v["tp"]})
    clean.sort(key=lambda d: (-d["payout"], -(d["win_rate"] or 0)))

    print(f"\n[gauntlet:{st}] {len(clean)} of {len(cands)} survived 2016-2025 with 0 breaches",
          flush=True)
    for d in clean[:10]:
        print(f"   trial {d['trial']:>4}  payout ${d['payout']:>10,.0f}  net ${d['net']:>10,.0f}  "
              f"win {d['win_rate']}%  worstDDD {d['worst_ddd']:.2f}%  worstTDD {d['worst_tdd']:.2f}%",
              flush=True)

    if clean:
        best = clean[0]
        w5.atomic_write(w5.W5_DIR / "current_best.json",
                        {"from_stage": st, "trial": best["trial"],
                         "payout": best["payout"], "win_rate": best["win_rate"],
                         "env": best["env"], "tp": best["tp"]})
        print(f"\n[gauntlet:{st}] current_best.json <- trial {best['trial']} "
              f"(payout ${best['payout']:,.0f}) — next stage builds on this", flush=True)
    else:
        print(f"\n[gauntlet:{st}] NO survivor. current_best.json unchanged; the stage "
              f"produced nothing that clears 2016-2025 without a breach.", flush=True)
    w5.atomic_write(w5.W5_DIR / f"{st}_survivors.json", clean)
    print(f"[w5_gauntlet:{st}] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
