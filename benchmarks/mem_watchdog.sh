#!/bin/bash
# mem_watchdog.sh — kill the complexity runner cleanly before the kernel OOM-freezes the box.
# Fires when MemAvailable + SwapFree drops below FLOOR_KB.
# Usage: ./benchmarks/mem_watchdog.sh   (run in background alongside the C1 runner)

FLOOR_KB=$((1024 * 1024))   # 1 GB combined headroom floor
LOG=data/watchdog.log
INTERVAL=30

echo "$(date -Iseconds) watchdog started (floor=$((FLOOR_KB / 1024))MB available+swapfree)" >> "$LOG"

while true; do
    avail=$(awk '/MemAvailable/{a=$2} /SwapFree/{s=$2} END{print a+s}' /proc/meminfo)
    if [ "$avail" -lt "$FLOOR_KB" ]; then
        pids=$(pgrep -f "benchmarks.run_" || true)
        if [ -n "$pids" ]; then
            echo "$(date -Iseconds) LOW MEMORY ($((avail / 1024))MB free) — killing runner pids: $pids" >> "$LOG"
            kill $pids 2>/dev/null
            sleep 10
            kill -9 $pids 2>/dev/null
            echo "$(date -Iseconds) runner stopped; partial results saved on disk, safe to resume" >> "$LOG"
        else
            echo "$(date -Iseconds) LOW MEMORY ($((avail / 1024))MB free) but no runner found" >> "$LOG"
        fi
        exit 1
    fi
    # also exit when the runner is done so the watchdog doesn't linger forever
    if ! pgrep -f "benchmarks.run_" > /dev/null; then
        echo "$(date -Iseconds) runner finished — watchdog exiting" >> "$LOG"
        exit 0
    fi
    sleep "$INTERVAL"
done
