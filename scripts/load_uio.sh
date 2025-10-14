#!/usr/bin/env bash
set -euo pipefail
make -C kernel
sudo modprobe uio || true
sudo insmod kernel/uio_sim_sensor.ko || (echo "insmod failed. Are you in an unprivileged container? Use --backend shm." && exit 1)
ls -l /dev/uio*
