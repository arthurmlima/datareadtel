#!/usr/bin/env bash
set -euo pipefail
BACKEND="${1:-uio}"
if [ "$BACKEND" = "uio" ]; then
  python3 sim/sim_writer.py --backend uio --uio /dev/uio0
else
  python3 sim/sim_writer.py --backend shm
fi
