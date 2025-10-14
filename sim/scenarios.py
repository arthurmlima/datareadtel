
import math

def loiter_brasilia(t):
    """Return dict of sensor values for a gentle loiter over Brasília."""
    omega = 0.5
    ax = 0.1 * math.sin(omega * t)
    ay = 0.1 * math.cos(omega * t)
    az = 9.81

    gx = 0.01 * math.sin(0.7 * t)
    gy = 0.01 * math.cos(0.7 * t)
    gz = 0.02 * math.sin(0.2 * t)

    mx, my, mz = 25.0, 0.0, 40.0
    press = 101325.0 - 12.0 * math.sin(0.1 * t)
    tempc = 25.0 + 0.2 * math.sin(0.05 * t)

    lat = -15.793889 + 0.0001 * math.sin(0.001 * t)
    lon = -47.882778 + 0.0001 * math.cos(0.001 * t)
    alt = 1100.0 + 2.0 * math.sin(0.01 * t)
    airspeed = 15.0 + 2.0 * math.sin(0.3 * t)
    bat_v = 12.3 - 0.0001 * t
    bat_i = 2.1 + 0.1 * math.sin(0.5 * t)

    return dict(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
                mx=mx, my=my, mz=mz, press=press, tempc=tempc,
                lat=lat, lon=lon, alt=alt, airspeed=airspeed,
                bat_v=bat_v, bat_i=bat_i)

def eddf_approach(t):
    """Return dict of sensor values for a looping straight-in approach to EDDF."""
    EDDF_LAT = 50.0379
    EDDF_LON = 8.5622
    FIELD_ELEV_M = 111.0

    START_LAT = 50.0400
    START_LON = 8.3500
    START_ALT = 900.0
    START_KT  = 80.0
    END_KT    = 65.0
    APPROACH_SEC = 360.0

    phase = (t % APPROACH_SEC) / APPROACH_SEC  # loop
    def lerp(a,b,s): 
        s = 0.0 if s < 0.0 else 1.0 if s > 1.0 else s
        return a + (b - a) * s

    lat = lerp(START_LAT, EDDF_LAT, phase)
    lon = lerp(START_LON, EDDF_LON, phase)
    alt = lerp(START_ALT, FIELD_ELEV_M + 5.0, phase)

    kt_to_ms = 0.514444
    airspeed = lerp(START_KT, END_KT, phase) * kt_to_ms + 0.8 * math.sin(0.6 * t)

    ax = 0.05 * math.sin(0.4 * t)
    ay = 0.03 * math.sin(0.9 * t + 1.2)
    az = 9.81 + 0.02 * math.sin(1.3 * t)

    gx = 0.02 * math.sin(0.5 * t)
    gy = 0.01 * math.cos(0.6 * t)
    gz = 0.03 * math.sin(0.2 * t)

    press_sl = 101325.0
    press = press_sl + (-12.0 * math.sin(0.1 * t)) - (alt * 12.0) / 100.0
    tempc = 15.0 - 0.0065 * alt + 0.3 * math.sin(0.03 * t)

    bat_v = 12.3 - 0.0001 * t
    bat_i = 2.1 + 0.1 * math.sin(0.5 * t)

    return dict(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
                mx=25.0, my=0.0, mz=40.0, press=press, tempc=tempc,
                lat=lat, lon=lon, alt=alt, airspeed=airspeed,
                bat_v=bat_v, bat_i=bat_i)
