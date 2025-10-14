
#!/usr/bin/env python3
import argparse, mmap, os, struct, time
from common.registers import *

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=['uio','shm'], default='uio')
    ap.add_argument('--uio', default=DEFAULT_UIO)
    ap.add_argument('--shm', default=DEFAULT_SHM_PATH)
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    if args.backend == 'uio':
        fd = os.open(args.uio, os.O_RDONLY)
    else:
        fd = os.open(args.shm, os.O_RDONLY)

    mem = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
    try:
        for _ in range(args.count):
            mem.seek(TICK_US)
            t = struct.unpack('<I', mem.read(4))[0]
            print(t)
            time.sleep(0.2)
    finally:
        mem.close(); os.close(fd)

if __name__ == "__main__":
    main()
