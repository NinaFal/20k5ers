#!/usr/bin/env python3
"""
Shared harness for the 100k / 5%-daily-wall optimization round.

Design notes that matter:

* **5% wall, not 3%.** Everything in the previous round was scored against the
  Summer Edition's 3% wall. `challenge_score.run_step` defaults to 3% unless the
  caller passes CFG_DAILY_WALL_PCT explicitly, so BASE_ENV sets it to 5.0 here.

* **Same 100 canonical start dates for every stage**, so stage results are
  directly comparable and a later stage cannot look better merely by landing on
  friendlier windows.

* **Per (config, start) caching in a TRACKED json.** This container restarts
  every few minutes and has rebuilt itself from scratch once, wiping every
  gitignored file. Results live in git; only scratch lives in .db/.log.

* **Breach is a hard reject with early abort.** A config that breaches anywhere
  is rejected regardless of speed, so there is no reason to pay for the
  remaining windows once one has breached.

* **Screen, then validate.** Scoring every config on all 100 starts is 200
  backtests per config — infeasible here. Stages rank on a screen subset; the
  top N are then re-scored on the full 100 AND run through the 2016-2025
  gauntlet, and only 0-breach survivors advance. Selection therefore happens on
  the full evidence even though ranking uses a subset.
"""
import concurrent.futures, importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
W5_DIR = DOE_DIR / "wall5"
W5_DIR.mkdir(parents=True, exist_ok=True)

_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

WORKERS = int(os.environ.get("W5_WORKERS", str(os.cpu_count() or 2)))
CANON = json.loads((DOE_DIR / "CANONICAL_100_STARTS.json").read_text())["starts"]
TARGET_DAYS = 30          # both steps passed within 30 calendar days
HORIZON = 75

# ── Baseline: the best-validated config from the 3% round, re-pointed at 5% ──
BASE_ENV = {
    "RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
    "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64", "VOL_REGIME_DD_OFF": "5.0",
    "CFG_DAILY_HALT_PCT": "3.5",          # scaled for a 5% wall (was 2.0 at 3%)
    "CFG_MAX_CUM_RISK": "3.0",
    "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5",
    "CFG_TDD_WARNING_PCT": "3.0", "CFG_RISK_CONSERVATIVE": "0.3",
    "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
    "TDD_WALL_SAFETY": "4.0",
    "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
    # XRP en ADA staan in CRYPTO_ASSETS maar 5ers biedt ze niet aan, dus ze
    # horen niet in de universe. Tot nu toe werden ze stil overgeslagen omdat
    # er geen data voor was; sinds die data er wel is moeten ze expliciet weg,
    # anders handelt de backtest instrumenten die live niet bestaan.
    # BTC en ETH staan er sinds de decade-vergelijking uit. Met crypto komt
    # opgenomen plus eindbalans over elf jaar op $4.069.877 uit, zonder op
    # $4.107.981 — crypto kost 0,93%. Dat is ruis, maar het levert ook niets
    # op, en het kost gemiddeld 0,32 punt dagelijkse drawdown in de jaren
    # waarin het meedoet (2,70% tegen 2,39%, hoger in 5 van 9 jaren) op een
    # muur van 5%. Daar komt bij dat crypto op 1:2 staat tegen 1:100 voor
    # forex: een enkele ETH-positie at 21,7% van het margeplafond waar een
    # forexpositie 2% pakt. Terugzetten is een regel: haal BTC_USD,ETH_USD
    # hier weg en draai w5_decade_crypto.py opnieuw voor beide armen.
    # AUD_NZD, EUR_NZD en AUD_JPY zijn hier TERUGGEZET. Ze stonden uit op het
    # oordeel "structureel net-negatief in beide helften", en dat oordeel houdt
    # geen stand op de huidige data en configuratie. Gemeten over elf jaar met de
    # arm 'fxpairs': $4.550.460 tegen $4.107.981, +10,8%, en over 2017-2025 met
    # beide armen op de $500k-cap $335 winst per trade tegen $318.
    #
    # Dat is geen gratis verbetering en dat hoort hier te staan: de dagelijkse
    # drawdown is in 8 van de 9 vergelijkbare jaren HOGER (gemiddeld 2,57% tegen
    # 2,39%) en de ergste totale drawdown over 2017+ gaat van 3,6% naar 4,6%.
    # De keuze is bewust gemaakt: meer winst tegen meer dagelijkse drawdown, met
    # nog ruime marge tot de muur van 5%.
    # NAS100_USD eruit. Het is het enige symbool dat in BEIDE helften geld
    # kost: -$41 per trade over 2015-2019 en -$122 over 2020-2025, profit factor
    # 0,72 over 164 trades. Het wint vaak genoeg (61,6%) maar verliest dubbel zo
    # groot als het wint: gemiddelde winst $329 tegen gemiddeld verlies -$731.
    # Dat is het patroon dat je op winratio niet ziet en op verwachtingswaarde
    # wel.
    #
    # Bijvangst: hiermee verdwijnt ook de datavervuiling uit
    # W5_DATA_INTEGRITY.md. Naast het echte M15-bestand lag
    # NAS100_USD_M15_2020_2025.csv met 751 DAGbars, die na ontdubbelen de echte
    # M15-bar om 00:00 verdrongen — een bar met het bereik van een hele dag,
    # vermomd als vijftien minuten. Een uitgesloten symbool wordt niet geladen,
    # dus dat probleem is weg in plaats van verplaatst.
    # UK100_USD eruit. Het stond elf jaar in het universum zonder ooit te
    # handelen, omdat het enige databestand dagbars bevatte onder een M15-naam.
    # Met echte data van OANDA (229.913 M15-bars vanaf 2015) handelt het wel,
    # maar levert het $20 per trade op bij een win rate van 49% — de onderkant
    # van de lijst, waar de beste symbolen $250 tot $300 doen.
    #
    # LET OP: dat cijfer komt van 112 trades over 2015-2017, drie van de elf
    # jaar. De volledige studie liep nog toen dit besloten werd. Terugzetten is
    # deze regel inkorten; de data blijft staan.
    #
    # Hiermee staan ALLE indices uit (NAS100 al eerder, SPX500 nooit aan
    # geweest). Het universum is daarmee puur FX plus goud en zilver.
    "EXCLUDE_SYMBOLS": "XRP_USD,ADA_USD,BTC_USD,ETH_USD,NAS100_USD,UK100_USD",
    "BROKER_TYPE": "fiveers_live",
    "CFG_DAILY_WALL_PCT": "5.0",          # <-- the whole point of this round
    "FIVEERS_MAX_SCALE": "500000",        # 100k scales up to 500k
    "NIGHTLY_DERISK": "1", "NIGHTLY_DERISK_HOUR": "21",
    "NIGHTLY_MAX_PER_GROUP": "1", "NIGHTLY_MAX_TOTAL": "2",
    "NIGHTLY_R_CLOSE_LOSING": "0.0", "NIGHTLY_R_NEW": "0.5", "NIGHTLY_REDUCE_PCT": "0.5",
}
BASE_TP = dict(scr.PINNED_ENTRY)
BASE_TP.update({
    "entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
    "fib_vol_ratio_threshold": 1.05,
    "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
    "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
    "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
    "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
    "sl_after_tp1_r": 0.2, "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2,
    "risk_per_trade_pct": 1.1,
})


# ── cache helpers ────────────────────────────────────────────────────────────
def atomic_write(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


def load_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        try:
            os.replace(path, path.with_suffix(".corrupt"))
        except OSError:
            pass
        return {} if default is None else default


def config_key(env, tp):
    """Fingerprint only what differs from the baseline, so keys stay readable
    and a stage that touches 3 params does not invalidate another stage's cache."""
    de = {k: v for k, v in sorted(env.items()) if BASE_ENV.get(k) != v}
    dt = {k: v for k, v in sorted(tp.items()) if BASE_TP.get(k) != v}
    return json.dumps({"env": de, "tp": dt}, sort_keys=True)


# ── evaluation ───────────────────────────────────────────────────────────────
def evaluate(env, tp, starts, cache_path, horizon=HORIZON):
    """Two-step challenge over `starts`. Breach = hard reject, abort early.
    Cached per (config, start); a restart costs at most one start."""
    store = load_json(cache_path)
    ck = config_key(env, tp)
    mine = store.setdefault(ck, {})

    rows = [mine[s] for s in starts if s in mine]
    if any(r["breach"] for r in rows):
        return summarize(rows, aborted=True)

    todo = [s for s in starts if s not in mine]
    chunk = max(2, WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(cs.full_two_step, env, tp, s, horizon): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                rows.append(r); mine[futs[f]] = r
            atomic_write(cache_path, store)
            if any(r["breach"] for r in rows):
                return summarize(rows, aborted=True)
    return summarize(rows, aborted=False)


def summarize(rows, aborted):
    n = max(len(rows), 1)
    br = sum(1 for r in rows if r["breach"]) / n
    if aborted or br > 0:
        return {"breach_rate": round(br, 3), "p_target": 0.0, "p30": 0.0,
                "p40": 0.0, "p50": 0.0, "complete_rate": 0.0,
                "median_days": None, "fastest": None, "n": len(rows), "aborted": aborted}
    tot = sorted(r["total"] for r in rows if r.get("total") is not None)
    return {"breach_rate": 0.0,
            "complete_rate": round(len(tot) / n, 3),
            # p_target is the objective; p30/p40/p50 are reported alongside so a
            # change of target never silently redefines what the numbers mean.
            "p_target": round(sum(1 for t in tot if t <= TARGET_DAYS) / n, 3),
            "p30": round(sum(1 for t in tot if t <= 30) / n, 3),
            "p40": round(sum(1 for t in tot if t <= 40) / n, 3),
            "p50": round(sum(1 for t in tot if t <= 50) / n, 3),
            "median_days": (tot[len(tot) // 2] if tot else None),
            "fastest": (tot[0] if tot else None),
            "n": len(rows), "aborted": False}


def score_of(m):
    """Breach is absolute. Then: pass-within-50-days, completions, raw speed."""
    if m["breach_rate"] > 0:
        return -1e6 * m["breach_rate"]
    if not m["complete_rate"]:
        return -1000.0
    # Rate of passing inside TARGET_DAYS dominates; completions and raw speed
    # only break ties between configs that hit the target equally often.
    return 1000.0 * m["p_target"] + 200.0 * m["complete_rate"] - float(m["median_days"])


# ── 2016-2025 gauntlet (the 0-breach filter between stages) ──────────────────
def decade_run(env, tp, year, balance=100_000.0):
    """One calendar year as a fresh $100k funded account. Chunked by year because
    a single 10-year subprocess cannot survive this container's restart cadence."""
    e = dict(os.environ); e.update(cs.dh.BASE_ENV); e.update(env)
    e["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", f"{year}-01-01",
                        "--end", f"{year}-12-31", "--balance", f"{balance:.2f}",
                        "--output", td, "--quiet"],
                       env=e, cwd=str(cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=7200)
        rj = Path(td) / "results.json"
        if not rj.exists():
            return {"error": "no results"}
        r = json.loads(rj.read_text())
        return {"net_pnl": r.get("net_pnl"), "withdrawn": r.get("fiveers_total_withdrawn"),
                "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "account_failed": r.get("account_failed"),
                "fail_reason": (r.get("fail_info") or {}).get("reason")}
    finally:
        shutil.rmtree(td, ignore_errors=True)


DECADE_YEARS = list(range(2016, 2026))
