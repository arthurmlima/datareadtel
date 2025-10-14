#!/usr/bin/env bash
set -euo pipefail
gcc -O2 -o examples/reader examples/reader.c
./examples/reader ${1:-/dev/uio0}
