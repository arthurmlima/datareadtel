
#!/usr/bin/env python3
import argparse, mmap, os, struct, time, math, random, sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.registers import *
from sim.scenarios import loiter_brasilia, eddf_approach

def ensure_shm(path, size):
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    os.ftruncate(fd, size)
    return fd

def open_map(backend, uio_path, shm_path):
    if backend == "uio":
        fd = os.open(uio_path, os.O_RDWR | os.O_SYNC)
        mm = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        return fd, mm
    elif backend == "shm":
        fd = ensure_shm(shm_path, PAGE_SIZE)
        mm = mmap.mmap(fd, PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        return fd, mm
    else:
        raise SystemExit("unknown backend: " + backend)

def pack_u32(mem, off, v): mem.seek(off); mem.write(struct.pack('<I', v & 0xffffffff))
def pack_f32(mem, off, v): mem.seek(off); mem.write(struct.pack('<f', float(v)))
def pack_f64(mem, off, v): mem.seek(off); mem.write(struct.pack('<d', float(v)))
def rd_u32(mem, off): mem.seek(off); return struct.unpack('<I', mem.read(4))[0]

def main():
    ap = argparse.ArgumentParser(description="Flight sensor simulator (UIO or SHM)")
    ap.add_argument('--backend', choices=['uio','shm'], default='uio',
                    help='memory backend: uio (/dev/uio0) or shm (/dev/shm file)')
    ap.add_argument('--uio', default=DEFAULT_UIO, help='uio device path')
    ap.add_argument('--shm', default=DEFAULT_SHM_PATH, help='shm file path')
    ap.add_argument('--rate', type=float, default=100.0, help='update rate in Hz')
    args = ap.parse_args()

    fd, mem = open_map(args.backend, args.uio, args.shm)

    # Header/init
    pack_u32(mem, MAGIC, 0x53554D31)
    pack_u32(mem, VERSION, 0x00010000)
    pack_u32(mem, STATUS, 0x1)
    seed = int(time.time()) & 0xffffffff
    pack_u32(mem, RNG_SEED, seed)
    random.seed(seed)

    print(f"[sim] backend={args.backend} rate={args.rate}Hz | CTRL bits: 0=freeze 1=scenario(0 loiter,1 EDDF) 2=noise")
    period = 1.0 / max(1e-6, args.rate)
    start = time.time()

    try:
        while True:
            now = time.time()
            t = now - start
            pack_u32(mem, TICK_US, int(t * 1e6))

            ctrl = rd_u32(mem, CTRL)
            if ctrl & 0x1:    # freeze
                time.sleep(period)
                continue

            # Choose scenario (bit1)
            vals = eddf_approach(t) if (ctrl & 0x2) else loiter_brasilia(t)

            # Optional noise (bit2)
            if ctrl & 0x4:
                def n(s, sd=0.02): return s + random.gauss(0, sd)
                for k in ['ax','ay','az','gx','gy','gz']:
                    vals[k] = n(vals[k])
                vals['press'] = n(vals['press'], 1.5)
                vals['tempc'] = n(vals['tempc'], 0.1)
                vals['airspeed'] = n(vals['airspeed'], 0.2)

            # Write all registers
            pack_f32(mem, ACCEL_X, vals['ax']); pack_f32(mem, ACCEL_Y, vals['ay']); pack_f32(mem, ACCEL_Z, vals['az'])
            pack_f32(mem, GYRO_X,  vals['gx']); pack_f32(mem, GYRO_Y,  vals['gy']); pack_f32(mem, GYRO_Z,  vals['gz'])
            pack_f32(mem, MAG_X,   vals['mx']); pack_f32(mem, MAG_Y,   vals['my']); pack_f32(mem, MAG_Z,   vals['mz'])
            pack_f32(mem, BARO_P,  vals['press']); pack_f32(mem, BARO_T, vals['tempc'])
            pack_f64(mem, GPS_LAT64, vals['lat']); pack_f64(mem, GPS_LON64, vals['lon']); pack_f32(mem, GPS_ALT, vals['alt'])
            pack_f32(mem, AIRSPEED, vals['airspeed'])
            pack_f32(mem, BAT_V, vals['bat_v']); pack_f32(mem, BAT_I, vals['bat_i'])

            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        mem.close()
        os.close(fd)

if __name__ == '__main__':
    main()
