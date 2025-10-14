
# Offsets for the fake sensor register block
MAGIC     = 0x000
VERSION   = 0x004
STATUS    = 0x008
TICK_US   = 0x00C
ACCEL_X   = 0x010
ACCEL_Y   = 0x014
ACCEL_Z   = 0x018
GYRO_X    = 0x01C
GYRO_Y    = 0x020
GYRO_Z    = 0x024
MAG_X     = 0x028
MAG_Y     = 0x02C
MAG_Z     = 0x030
BARO_P    = 0x034
BARO_T    = 0x038
GPS_LAT64 = 0x03C
GPS_LON64 = 0x044
GPS_ALT   = 0x04C
AIRSPEED  = 0x050
BAT_V     = 0x054
BAT_I     = 0x058
RNG_SEED  = 0x100
CTRL      = 0x104

PAGE_SIZE = 4096
DEFAULT_SHM_PATH = "/dev/shm/sim_sensor.bin"
DEFAULT_UIO = "/dev/uio0"
