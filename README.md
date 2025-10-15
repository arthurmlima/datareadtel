
# Flight Sensor Sim (UIO MMIO + SHM fallback)

A minimal, **register-level** fake sensor device that your telemetry stack can read as if it's a real memory-mapped device. Two backends:

- **UIO (Userspace I/O)**: kernel module exposes `/dev/uio0` (best on a real Linux board).
- **SHM fallback**: unprivileged shared-memory file (works in containers/GitHub Codespaces).

Both provide the exact same 4 KB register map.

## Register Map (Offsets, little-endian)
```
0x000 MAGIC      u32  = 0x53554D31 ("SUM1")
0x004 VERSION    u32  = 0x00010000
0x008 STATUS     u32  bit0=OK bit1=SensorFail bit2=GPSLock
0x00C TICK_US    u32  wraps
0x010 ACCEL_X    f32  m/s^2
0x014 ACCEL_Y    f32
0x018 ACCEL_Z    f32
0x01C GYRO_X     f32  rad/s
0x020 GYRO_Y     f32
0x024 GYRO_Z     f32
0x028 MAG_X      f32  uT
0x02C MAG_Y      f32
0x030 MAG_Z      f32  uT
0x034 BARO_PRESS f32  Pa
0x038 BARO_TEMP  f32  C
0x03C GPS_LAT    f64  deg
0x044 GPS_LON    f64  deg
0x04C GPS_ALT    f32  m
0x050 AIRSPEED   f32  m/s
0x054 BATTERY_V  f32  V
0x058 BATTERY_I  f32  A
0x100 RNG_SEED   u32
0x104 CTRL       u32  bit0=freeze, bit1=scenario(0 loiter,1 EDDF), bit2=noise
```
Total size: 4096 bytes.

## Quick Start (SHM backend: works in Codespaces)
```
# 1) Launch simulator (updates at 100 Hz)
python3 sim/sim_writer.py --backend shm

# 2) Print moving values
python3 tools/print_values.py --backend shm

# 3) Toggle scenarios
python3 tools/ctrl.py --backend shm --set 2        # bit1=1 (Frankfurt approach)
python3 tools/ctrl.py --backend shm --clear 2      # bit1=0 (Brasília loiter)
python3 tools/ctrl.py --backend shm --set 1        # freeze
python3 tools/ctrl.py --backend shm --clear 1      # unfreeze
```

## UIO backend (requires kernel build tools and loadable modules)
```
sudo apt-get update && sudo apt-get install -y build-essential linux-headers-$(uname -r)
make -C kernel
sudo modprobe uio || true
sudo insmod kernel/uio_sim_sensor.ko   # creates /dev/uio0

# Run simulator against /dev/uio0
python3 sim/sim_writer.py --backend uio --uio /dev/uio0

# Read
gcc -O2 -o examples/reader examples/reader.c
./examples/reader /dev/uio0
```

## Scenarios
- **Loiter (default)**: gentle circular drift over Brasília with sine-like IMU.
- **Frankfurt approach (EDDF)**: 6‑minute straight-in descent; enable with CTRL bit1.

## Tools
- `tools/print_values.py`: prints a few live registers.
- `tools/ctrl.py`: set/clear CTRL bits.
- `tools/read_tick.py`: shows `TICK_US` increasing.

## Streaming over ADALM-Pluto (GNU Radio)
The repository now includes a GNU Radio-based flowgraph that samples the sensor
registers, converts them into MAVLink v2 telemetry and transmits them with a
GMSK waveform through an ADALM-Pluto SDR.

1. Start the simulator (SHM backend works well in a container):
   ```bash
   python3 sim/sim_writer.py --backend shm
   ```
2. In a second shell launch the transmitter, pointing it at the shared memory
   backend and configuring the desired RF parameters:
   ```bash
   python3 scripts/gr_pluto_mavlink.py \
       --backend shm \
       --samp-rate 1e6 \
       --tx-freq 915e6 \
       --tx-bw 200e3 \
       --tx-gain -10
   ```

The script can also run against `/dev/uio0` on hardware by switching the backend
to `uio` (default) and, if needed, overriding `--uio`.

## Notes
- If `insmod` fails in Codespaces/containers, use `--backend shm`.
- The reader and tools accept `--backend uio|shm`. For UIO you can pass the node path with `--uio` (default `/dev/uio0`). For SHM, the file is `/dev/shm/sim_sensor.bin`.
