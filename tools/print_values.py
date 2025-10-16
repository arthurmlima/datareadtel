
#!/usr/bin/env python3
import argparse, mmap, os, struct, time, sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.registers import *

def open_map(backend, uio_path, shm_path):
    if backend == "uio":
        fd = os.open(uio_path, os.O_RDONLY)
        mm = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        return fd, mm
    else:
        fd = os.open(shm_path, os.O_RDONLY)
        mm = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        return fd, mm

def rf32(mem, off): mem.seek(off); return struct.unpack('<f', mem.read(4))[0]
def ru32(mem, off): mem.seek(off); return struct.unpack('<I', mem.read(4))[0]
def rf64(mem, off): mem.seek(off); return struct.unpack('<d', mem.read(8))[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=['uio','shm'], default='uio')
    ap.add_argument('--uio', default=DEFAULT_UIO)
    ap.add_argument('--shm', default=DEFAULT_SHM_PATH)
    ap.add_argument('--count', type=int, default=20)
    ap.add_argument('--interval', type=float, default=0.2)
    args = ap.parse_args()

    fd, mem = open_map(args.backend, args.uio, args.shm)
    try:
        for _ in range(args.count):
            tick = ru32(mem, TICK_US)
            ax = rf32(mem, ACCEL_X); gz = rf32(mem, GYRO_Z); v = rf32(mem, AIRSPEED)
            lat = rf64(mem, GPS_LAT64); lon = rf64(mem, GPS_LON64); alt = rf32(mem, GPS_ALT)
            print(f"tick={tick:10d} ax={ax:+.3f} gz={gz:+.3f} v={v:5.2f} lat={lat:+.6f} lon={lon:+.6f} alt={alt:6.1f}")
            time.sleep(args.interval)
    finally:
        mem.close(); os.close(fd)

if __name__ == "__main__":
    main()
