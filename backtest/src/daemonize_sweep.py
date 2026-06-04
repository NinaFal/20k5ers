#!/usr/bin/env python3
"""
Double-fork daemon launcher for the Stage 1c sweep.
Reparents the sweep process to PID 1 so it survives session cleanup.
"""
import os
import sys

REPO    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT  = os.path.join(REPO, "backtest", "src", "run_stage1c.sh")
LOGFILE = os.path.join(REPO, "backtest", "output", "doe", "stage1c_live.log")

os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

# First fork — parent exits immediately
pid = os.fork()
if pid > 0:
    print(f"Daemon PID: {pid}  (detached, reparents to PID 1 after second fork)")
    sys.exit(0)

# Child: create new session (no controlling terminal)
os.setsid()

# Second fork — guarantees we can never reacquire a controlling terminal
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)

# Grandchild: fully detached daemon, reparented to init
os.chdir(REPO)

# Redirect stdin/out/err
with open("/dev/null", "r") as null:
    os.dup2(null.fileno(), 0)
log_fd = open(LOGFILE, "a")
os.dup2(log_fd.fileno(), 1)
os.dup2(log_fd.fileno(), 2)
log_fd.close()

os.execv("/bin/bash", ["/bin/bash", SCRIPT])
