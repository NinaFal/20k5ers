#!/usr/bin/env bash
# Event monitor for the two live jobs: the 100-start holdout and the continuous
# scaling decade. Emits sparsely (every 10 completed starts, every finished year,
# every new breach, and the two DONE markers) and commits results on each event
# so a container rebuild costs nothing.
cd /home/user/20k5ers || exit 1
H=backtest/output/doe/wall5/holdout100.json
CC=backtest/output/doe/wall5/continuous_chunked.json
last_h=0; last_br=0; last_cc=""
save() {
  git add -A backtest/output/doe/wall5 >/dev/null 2>&1
  git commit -q -m "wall5: $1" >/dev/null 2>&1 || return 0
  for w in 2 4 8 16; do
    git push -q origin claude/awesome-maxwell-continued-k9zacp >/dev/null 2>&1 && return 0
    sleep "$w"
  done
}
for ((i = 0; i < 10000; i++)); do
  if [ -f "$H" ]; then
    read -r n br med p30 fast <<<"$(uv run python3 -c '
import json,sys
r=json.load(open("'"$H"'"))
t=sorted(v["total"] for v in r.values() if v.get("total") is not None)
br=sum(1 for v in r.values() if v.get("breach"))
print(len(r),br,(t[len(t)//2] if t else "-"),(sum(1 for x in t if x<=30) if t else 0),(t[0] if t else "-"))
' 2>/dev/null)"
    n=${n:-0}; br=${br:-0}
    if [ "$n" -ge $((last_h + 10)) ] || [ "$br" -gt "$last_br" ]; then
      echo "[holdout] $n/100 done | breaches $br | median ${med}d | <=30d $p30 | fastest ${fast}d"
      last_h=$n; last_br=$br
      save "holdout100 progress $n/100 (breaches $br)"
    fi
  fi
  cc=$(grep -E "^\[cc\] .*: level|^\[cc\] .*(SURVIVED|DIED)" backtest/output/doe/wall5/continuous_chunked_run.log 2>/dev/null | tail -1)
  if [ -n "$cc" ] && [ "$cc" != "$last_cc" ]; then
    echo "$cc"; last_cc="$cc"
    save "continuous scaling progress"
  fi
  if grep -q "w5_holdout100. DONE_MARKER" backtest/output/doe/wall5/holdout100_run.log 2>/dev/null &&
     grep -q "w5_continuous_chunked. DONE_MARKER" backtest/output/doe/wall5/continuous_chunked_run.log 2>/dev/null; then
    echo "[watch] BOTH JOBS COMPLETE"
    save "holdout + continuous complete"
    exit 0
  fi
  sleep 45
done
