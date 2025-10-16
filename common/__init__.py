"""Shared register definitions for datareadtel simulators."""

__all__ = [
    'MAGIC', 'VERSION', 'STATUS', 'TICK_US', 'ACCEL_X', 'ACCEL_Y', 'ACCEL_Z',
    'GYRO_X', 'GYRO_Y', 'GYRO_Z', 'MAG_X', 'MAG_Y', 'MAG_Z', 'BARO_P', 'BARO_T',
    'GPS_LAT64', 'GPS_LON64', 'GPS_ALT', 'AIRSPEED', 'BAT_V', 'BAT_I',
    'RNG_SEED', 'CTRL', 'PAGE_SIZE', 'DEFAULT_SHM_PATH', 'DEFAULT_UIO'
]

from .registers import *  # noqa: F401,F403
