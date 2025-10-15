#!/usr/bin/env python3
"""Transmit simulated flight sensor data as MAVLink frames over an ADALM-Pluto radio.

This script bridges the fake sensor register block that ships with this repository
into a GNU Radio flowgraph.  Values are periodically sampled, converted into
standard MAVLink v2 telemetry (HIL_SENSOR + HIL_GPS) and pushed through a simple
GMSK modem before being handed to the Pluto SDR front-end.

The flowgraph layout is:

    Sensor registers -> MAVLink PDU -> tagged stream -> bit unpack ->
    GMSK modulator -> Pluto sink

It can be exercised on a development machine using the shared-memory backend
(`sim/sim_writer.py --backend shm`) and later switched to the UIO backend on the
embedded target.
"""

import argparse
import logging
import mmap
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

import pmt
from gnuradio import blocks, digital, gr, iio
from pymavlink.dialects.v20 import common as mavlink2

from common import registers


_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorSample:
    """Container for one sensor snapshot."""

    tick_us: int
    accel: tuple
    gyro: tuple
    mag_ut: tuple
    baro_press_pa: float
    baro_temp_c: float
    gps_lat_deg: float
    gps_lon_deg: float
    gps_alt_m: float
    airspeed_mps: float


class _SensorRegisterReader:
    """Minimal helper that exposes the register page as a Python mapping."""

    def __init__(self, backend: str, uio_path: str, shm_path: str):
        self._backend = backend
        self._uio_path = uio_path
        self._shm_path = shm_path
        self._fd: Optional[int] = None
        self._mem: Optional[mmap.mmap] = None

    def open(self) -> None:
        if self._mem is not None:
            return
        if self._backend == "uio":
            path = self._uio_path
            flags = os.O_RDONLY
        else:
            path = self._shm_path
            flags = os.O_RDONLY
        _LOGGER.info("Opening sensor backend %s (%s)", self._backend, path)
        fd = os.open(path, flags)
        mem = mmap.mmap(fd, registers.PAGE_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        self._fd = fd
        self._mem = mem

    def close(self) -> None:
        if self._mem is not None:
            self._mem.close()
            self._mem = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _read_u32(self, offset: int) -> int:
        assert self._mem is not None
        self._mem.seek(offset)
        return struct.unpack("<I", self._mem.read(4))[0]

    def _read_f32(self, offset: int) -> float:
        assert self._mem is not None
        self._mem.seek(offset)
        return struct.unpack("<f", self._mem.read(4))[0]

    def _read_f64(self, offset: int) -> float:
        assert self._mem is not None
        self._mem.seek(offset)
        return struct.unpack("<d", self._mem.read(8))[0]

    def read_sample(self) -> SensorSample:
        if self._mem is None:
            raise RuntimeError("sensor not opened")
        tick = self._read_u32(registers.TICK_US)
        accel = (
            self._read_f32(registers.ACCEL_X),
            self._read_f32(registers.ACCEL_Y),
            self._read_f32(registers.ACCEL_Z),
        )
        gyro = (
            self._read_f32(registers.GYRO_X),
            self._read_f32(registers.GYRO_Y),
            self._read_f32(registers.GYRO_Z),
        )
        mag = (
            self._read_f32(registers.MAG_X),
            self._read_f32(registers.MAG_Y),
            self._read_f32(registers.MAG_Z),
        )
        baro_press = self._read_f32(registers.BARO_P)
        baro_temp = self._read_f32(registers.BARO_T)
        gps_lat = self._read_f64(registers.GPS_LAT64)
        gps_lon = self._read_f64(registers.GPS_LON64)
        gps_alt = self._read_f32(registers.GPS_ALT)
        airspeed = self._read_f32(registers.AIRSPEED)
        return SensorSample(
            tick_us=tick,
            accel=accel,
            gyro=gyro,
            mag_ut=mag,
            baro_press_pa=baro_press,
            baro_temp_c=baro_temp,
            gps_lat_deg=gps_lat,
            gps_lon_deg=gps_lon,
            gps_alt_m=gps_alt,
            airspeed_mps=airspeed,
        )


class SensorMavlinkSource(gr.basic_block):
    """GNU Radio block that publishes MAVLink PDUs."""

    def __init__(
        self,
        backend: str,
        uio_path: str,
        shm_path: str,
        rate_hz: float,
        sysid: int,
        compid: int,
    ):
        gr.basic_block.__init__(self, name="sensor_mavlink_source", in_sig=None, out_sig=None)
        self._reader = _SensorRegisterReader(backend, uio_path, shm_path)
        self._rate_hz = float(rate_hz)
        self._period = 1.0 / self._rate_hz
        self._sysid = sysid
        self._compid = compid
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mav = mavlink2.MAVLink(None)
        self._mav.srcSystem = sysid
        self._mav.srcComponent = compid
        self._out_port = pmt.intern("mavlink")
        self.message_port_register_out(self._out_port)

    def start(self):
        _LOGGER.info("Starting sensor source thread @ %.1f Hz", self._rate_hz)
        self._reader.open()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return super().start()

    def stop(self):
        _LOGGER.info("Stopping sensor source thread")
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._reader.close()
        return super().stop()

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            start = time.perf_counter()
            try:
                sample = self._reader.read_sample()
                payload = self._encode_sample(sample)
                pdu = pmt.cons(pmt.PMT_NIL, pmt.init_u8vector(len(payload), payload))
                self.message_port_pub(self._out_port, pdu)
            except Exception:  # pragma: no cover - defensive logging
                _LOGGER.exception("Failed to publish MAVLink packet")
            elapsed = time.perf_counter() - start
            remaining = self._period - elapsed
            if remaining > 0:
                self._stop_evt.wait(remaining)

    def _encode_sample(self, sample: SensorSample) -> bytes:
        tick_us = sample.tick_us

        # Build HIL_SENSOR message
        accel = sample.accel
        gyro = sample.gyro
        mag_gauss = tuple(v / 100.0 for v in sample.mag_ut)  # µT -> gauss
        abs_press_mbar = sample.baro_press_pa / 100.0
        rho = 1.225  # kg/m³ at sea level
        diff_press_pa = 0.5 * rho * sample.airspeed_mps ** 2
        diff_press_mbar = diff_press_pa / 100.0
        pressure_alt = sample.gps_alt_m
        temperature_k = sample.baro_temp_c + 273.15
        fields_updated = 0x1FFF  # all 13 fields set

        hil_sensor = self._mav.hil_sensor_encode(
            time_us=tick_us,
            xacc=accel[0],
            yacc=accel[1],
            zacc=accel[2],
            xgyro=gyro[0],
            ygyro=gyro[1],
            zgyro=gyro[2],
            xmag=mag_gauss[0],
            ymag=mag_gauss[1],
            zmag=mag_gauss[2],
            abs_pressure=abs_press_mbar,
            diff_pressure=diff_press_mbar,
            pressure_alt=pressure_alt,
            temperature=temperature_k,
            fields_updated=fields_updated,
        )

        # Build HIL_GPS message
        lat_e7 = int(sample.gps_lat_deg * 1e7)
        lon_e7 = int(sample.gps_lon_deg * 1e7)
        alt_mm = int(sample.gps_alt_m * 1000)
        eph_cm = 50  # nominal accuracy placeholders
        epv_cm = 75
        velocity_cm_s = int(sample.airspeed_mps * 100)
        hil_gps = self._mav.hil_gps_encode(
            time_usec=tick_us,
            fix_type=3,
            lat=lat_e7,
            lon=lon_e7,
            alt=alt_mm,
            eph=eph_cm,
            epv=epv_cm,
            vel=velocity_cm_s,
            vn=0,
            ve=0,
            vd=0,
            cog=0,
            satellites_visible=10,
            id=0,
        )

        packed = hil_sensor.pack(self._mav) + hil_gps.pack(self._mav)
        _LOGGER.debug(
            "Published MAVLink payload: %d bytes (tick=%d)", len(packed), tick_us
        )
        return packed


class PlutoMavlinkTransmitter(gr.top_block):
    """Top block that modulates MAVLink frames and ships them to the Pluto SDR."""

    def __init__(self, args: argparse.Namespace):
        gr.top_block.__init__(self, "pluto_mavlink_tx")

        self.sensor = SensorMavlinkSource(
            backend=args.backend,
            uio_path=args.uio,
            shm_path=args.shm,
            rate_hz=args.sample_rate_hz,
            sysid=args.sysid,
            compid=args.compid,
        )

        self.pdu_to_stream = blocks.pdu_to_tagged_stream(blocks.byte_t, "packet_len")
        self.unpack_bits = blocks.unpack_k_bits_bb(8)
        self.mod = digital.gmsk_mod(samples_per_symbol=args.gmsk_sps, bt=args.gmsk_bt)

        self.tx = iio.pluto_sink(
            args.uri,
            int(args.tx_freq),
            int(args.samp_rate),
            int(args.tx_bw),
            int(args.tx_gain),
            int(args.buffer_size),
            False,
            args.normalize,
            args.quadrature,
            args.rf_port,
            args.filter,
            args.auto_filter,
        )

        self.msg_connect((self.sensor, "mavlink"), (self.pdu_to_stream, "pdus"))
        self.connect(self.pdu_to_stream, self.unpack_bits)
        self.connect(self.unpack_bits, self.mod)
        self.connect(self.mod, self.tx)


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backend",
        choices=["uio", "shm"],
        default="uio",
        help="Register backend to use (uio for /dev/uio0, shm for shared memory).",
    )
    ap.add_argument("--uio", default=registers.DEFAULT_UIO, help="Path to the UIO node.")
    ap.add_argument(
        "--shm",
        default=registers.DEFAULT_SHM_PATH,
        help="Path to the shared memory file for the SHM backend.",
    )
    ap.add_argument(
        "--sample-rate-hz",
        type=float,
        default=20.0,
        help="How often to sample the register map and emit MAVLink packets.",
    )
    ap.add_argument("--sysid", type=int, default=1, help="MAVLink system ID.")
    ap.add_argument("--compid", type=int, default=200, help="MAVLink component ID.")

    ap.add_argument("--uri", default="", help="IIO context URI (empty = auto-detect).")
    ap.add_argument(
        "--samp-rate",
        type=float,
        default=1_000_000,
        help="Baseband sample rate for the Pluto sink.",
    )
    ap.add_argument(
        "--tx-freq",
        type=float,
        default=915_000_000,
        help="RF transmit frequency in Hz.",
    )
    ap.add_argument(
        "--tx-bw",
        type=float,
        default=200_000,
        help="Front-end analog bandwidth in Hz.",
    )
    ap.add_argument("--tx-gain", type=int, default=-10, help="TX attenuation in dB (-89 to 0).")
    ap.add_argument(
        "--buffer-size",
        type=int,
        default=1 << 12,
        help="Number of samples per IIO buffer submission.",
    )
    ap.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize samples in the Pluto sink (maps to [-1, 1]).",
    )
    ap.add_argument(
        "--quadrature",
        type=float,
        default=0.0,
        help="Quadrature correction factor for Pluto sink.",
    )
    ap.add_argument(
        "--rf-port",
        default="A",
        choices=["A", "B"],
        help="Pluto RF port to use.",
    )
    ap.add_argument(
        "--filter",
        default="",
        help="Path to custom FIR filter file for the Pluto sink (optional).",
    )
    ap.add_argument(
        "--auto-filter",
        action="store_true",
        help="Let libiio design baseband filters automatically.",
    )
    ap.add_argument(
        "--gmsk-sps",
        type=int,
        default=4,
        help="Samples per symbol for the GMSK modulator.",
    )
    ap.add_argument(
        "--gmsk-bt",
        type=float,
        default=0.35,
        help="Gaussian BT product for the GMSK modulator.",
    )
    ap.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Python logging level.",
    )
    return ap


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    tb = PlutoMavlinkTransmitter(args)

    _LOGGER.info(
        "Launching flowgraph: freq=%.0f Hz samp_rate=%.0f Hz sysid=%d compid=%d",
        args.tx_freq,
        args.samp_rate,
        args.sysid,
        args.compid,
    )

    try:
        tb.start()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        _LOGGER.info("Interrupted, shutting down")
    finally:
        tb.stop()
        tb.wait()


if __name__ == "__main__":
    main()
