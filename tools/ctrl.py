
#!/usr/bin/env python3
import argparse, mmap, os, struct, sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.registers import *

def main():
    ap = argparse.ArgumentParser(description="Set/clear CTRL bits")
    ap.add_argument('--backend', choices=['uio','shm'], default='uio')
    ap.add_argument('--uio', default=DEFAULT_UIO)
    ap.add_argument('--shm', default=DEFAULT_SHM_PATH)
    ap.add_argument('--set', type=int, default=0, help='bit index to set (1-based)')
    ap.add_argument('--clear', type=int, default=0, help='bit index to clear (1-based)')
    args = ap.parse_args()

    if args.backend == 'uio':
        fd = os.open(args.uio, os.O_RDWR | os.O_SYNC)
    else:
        fd = os.open(args.shm, os.O_RDWR | os.O_SYNC)

    mem = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

    mem.seek(CTRL); val = struct.unpack('<I', mem.read(4))[0]
    original = val

    if args.set > 0:
        val |= (1 << (args.set-1))
    if args.clear > 0:
        val &= ~(1 << (args.clear-1))

    mem.seek(CTRL); mem.write(struct.pack('<I', val))
    mem.flush()

    print(f"CTRL: 0x{original:08X} -> 0x{val:08X}")
    mem.close(); os.close(fd)

if __name__ == "__main__":
    main()
