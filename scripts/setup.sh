#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y build-essential linux-headers-$(uname -r) python3 python3-pip
