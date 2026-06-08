#!/usr/bin/env python3
"""
moon_lines.py - the compass leg.

Companion to tidal_lines.py (the clock leg). Same spirit: pure math, no network,
a self-test that audits the method before any real fix is trusted, and an honest
statement of where the signal is clean and where it is not.

WHAT THIS DOES
  Given your position (latitude, longitude, and optionally altitude) and a moment
  in time, it computes WHERE THE MOON ACTUALLY IS from your spot:
      - azimuth   : the moon's compass bearing  (0=N, 90=E, 180=S, 270=W)
      - altitude  : how high above your horizon  (degrees; negative = below)
      - illum     : illuminated fraction          (0=new, 1=full) -> the phase
      - verdict   : GO / HOLD / STOP  (is this bearing usable right now)

  The azimuth is the compass. It is not pointing at a magnetic field that drifts
  and lies; it points at the real Moon, whose position is a geometric fact about
  where you stand on a rotating, sunlit Earth. That is the whole point.

WHERE THE INPUT COMES FROM
  The "What is my Elevation" Scriptable widget already calls Location.current(),
  which returns latitude, longitude and altitude in one object. That is exactly
  the input this needs. Phone acquires the geometry; this does the discrimination;
  the calendar precipitates downstream from this plus the tidal clock.

GO / HOLD / STOP - SAME GATE AS THE LEDGER, NEW CHANNEL
  The clock leg gates on "is M2/S2 a sharp line." The compass leg gates on
  "is the Moon usable as a bearing right now." Same go/hold/stop logic, a
  physical precondition instead of a magic threshold:

    STOP : Moon is below the horizon (alt < 0). No bearing. Don't pretend.
    HOLD : Moon is within HORIZON_BAND of the horizon. A bearing exists but
           parallax (~1 deg) and refraction (~0.5 deg) near the horizon make it
           untrustworthy. The HOLD band IS that uncertainty, named honestly.
    GO   : Moon is well above the horizon. Clean bearing.

  Second channel - the LUMINESCENT read (phosphor / bioluminescence keyed to
  actual moonlight) needs the Moon to be LIT, not just up. So it carries an
  extra gate on illuminated fraction: near new moon there is no light to drive
  the signal, so the light-based read is HOLD/STOP even when the geometric
  bearing is GO. The geometry doesn't care about phase; the photons do.

  Third channel - DOPPLER. The Earth-Moon range is not constant, so any signal
  referenced to the Moon (radar echo, moonbounce/EME, a laser ranging return)
  comes back shifted in frequency. Two real, additive, geometric contributions:
    ORBITAL    : the Moon's distance from Earth's centre breathes between
                 perigee and apogee over the ~27.3-day anomalistic month.
                 Read straight off the geocentric distance via a centred
                 numerical derivative - no extra theory needed.
    ROTATIONAL : you are not standing still. Earth's spin carries the observer
                 eastward at up to ~0.46 km/s (latitude-scaled), and whatever
                 component of THAT velocity points along the line of sight to
                 the Moon adds to (or fights) the orbital term. This is the
                 dominant, fast-varying part - the reason moonbounce operators
                 retune through a pass. It shares the bearing's az/alt geometry,
                 so it shares the bearing's gate: same HORIZON_BAND, third
                 channel, nothing new invented.
  Reported as a signed range-rate (m/s, + = receding/redshift, - = approaching/
  blueshift) and as a fractional shift in parts-per-billion, both one-way and
  doubled for an echo (the path closes or opens on both legs of a round trip).

PRECISION
  Low-precision lunar theory (Schlyter) with the main perturbation terms.
  Good to roughly 0.1-0.2 deg in bearing - far inside a compass's needs.
  Topocentric parallax is applied to ALTITUDE (it decides the horizon gate).
  Azimuth parallax and refraction are not modelled; that residual is exactly
  what the HOLD band absorbs. Falsifiable: the Moon's ecliptic longitude must
  advance ~12-14 deg/day. The self-test checks it.

USAGE
  python3 moon_lines.py                  # self-test (audit the method)
  python3 moon_lines.py 40.90 -80.86     # live fix at lat, lon (east +, west -)
  python3 moon_lines.py 40.90 -80.86 320 # ...with altitude in metres
"""

import sys, math
from datetime import datetime, timezone

# ---- degree-based trig ------------------------------------------------------
def sin(d): return math.sin(math.radians(d))
def cos(d): return math.cos(math.radians(d))
def tan(d): return math.tan(math.radians(d))
def asin(x): return math.degrees(math.asin(max(-1.0, min(1.0, x))))
def acos(x): return math.degrees(math.acos(max(-1.0, min(1.0, x))))
def atan2(y, x): return math.degrees(math.atan2(y, x))
def rev(d): return d % 360.0      # normalize to [0,360)

# ---- gate thresholds (the only knobs; both are physical, not magic) ---------
HORIZON_BAND = 10.0   # deg above horizon below which parallax+refraction blur the fix
ILLUM_MIN    = 0.10   # illuminated fraction below which the luminescent channel goes dark

# ---- physical constants for the Doppler channel (constants, not knobs) -----
EARTH_RADIUS_KM  = 6371.0       # mean radius -> converts geocentric distance and
                                # rotation rate into real-world km and km/s
SIDEREAL_DAY_S   = 86164.0905   # the clock Earth's spin actually runs on
LIGHT_SPEED_KM_S = 299792.458   # c -> converts a range-rate into a fractional shift


def day_number(dt_utc):
    """Schlyter day number d: days since 2000 Jan 0.0 UT, with fraction."""
    Y, M, D = dt_utc.year, dt_utc.month, dt_utc.day
    ut = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    d = 367*Y - (7*(Y + ((M+9)//12)))//4 + (275*M)//9 + D - 730530
    return d + ut/24.0


def _solve_kepler(M, e):
    """Eccentric anomaly (deg) from mean anomaly M (deg), eccentricity e."""
    E = M + (180.0/math.pi)*e*sin(M)*(1.0 + e*cos(M))
    for _ in range(6):
        dE = (E - (180.0/math.pi)*e*sin(E) - M) / (1.0 - e*cos(E))
        E -= dE
        if abs(dE) < 1e-6:
            break
    return E


def moon_position(d):
    """Geocentric apparent RA, Dec (deg) and distance (Earth radii) of the Moon,
    plus ecliptic lon/lat and the Sun's longitude (for phase). Schlyter, with the
    main perturbations."""
    # --- Sun (needed for perturbations, sidereal time, phase) ---
    w_s = 282.9404 + 4.70935e-5 * d
    M_s = rev(356.0470 + 0.9856002585 * d)
    L_s = rev(w_s + M_s)                      # Sun mean longitude

    # --- Moon orbital elements ---
    N = rev(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = rev(318.0634 + 0.1643573223 * d)
    a = 60.2666
    e = 0.054900
    M = rev(115.3654 + 13.0649929509 * d)

    E = _solve_kepler(M, e)
    x = a*(cos(E) - e)
    y = a*math.sqrt(1 - e*e)*sin(E)
    r = math.hypot(x, y)
    v = rev(atan2(y, x))

    # position in ecliptic coords
    xe = r*(cos(N)*cos(v+w) - sin(N)*sin(v+w)*cos(i))
    ye = r*(sin(N)*cos(v+w) + cos(N)*sin(v+w)*cos(i))
    ze = r*(sin(v+w)*sin(i))
    lon = rev(atan2(ye, xe))
    lat = atan2(ze, math.hypot(xe, ye))

    # --- main perturbations ---
    Lm = rev(N + w + M)        # Moon mean longitude
    Ms = M_s                   # Sun mean anomaly
    Mm = M                     # Moon mean anomaly
    Dl = rev(Lm - L_s)         # mean elongation
    F  = rev(Lm - N)           # argument of latitude

    lon += (-1.274*sin(Mm - 2*Dl)
            +0.658*sin(2*Dl)
            -0.186*sin(Ms)
            -0.059*sin(2*Mm - 2*Dl)
            -0.057*sin(Mm - 2*Dl + Ms)
            +0.053*sin(Mm + 2*Dl)
            +0.046*sin(2*Dl - Ms)
            +0.041*sin(Mm - Ms)
            -0.035*sin(Dl)
            -0.031*sin(Mm + Ms)
            -0.015*sin(2*F - 2*Dl)
            +0.011*sin(Mm - 4*Dl))
    lat += (-0.173*sin(F - 2*Dl)
            -0.055*sin(Mm - F - 2*Dl)
            -0.046*sin(Mm + F - 2*Dl)
            +0.033*sin(F + 2*Dl)
            +0.017*sin(2*Mm + F))
    r   += (-0.58*cos(Mm - 2*Dl)
            -0.46*cos(2*Dl))
    lon = rev(lon)

    # --- ecliptic -> equatorial ---
    ecl = 23.4393 - 3.563e-7 * d
    xg = r*cos(lon)*cos(lat)
    yg = r*sin(lon)*cos(lat)
    zg = r*sin(lat)
    xq = xg
    yq = yg*cos(ecl) - zg*sin(ecl)
    zq = yg*sin(ecl) + zg*cos(ecl)
    ra  = rev(atan2(yq, xq))
    dec = atan2(zq, math.hypot(xq, yq))

    return {"ra": ra, "dec": dec, "r": r,
            "lon": lon, "lat": lat, "sun_lon": L_s}


def local_sidereal_time(d, lon_east, ut_hours):
    """Local sidereal time in degrees."""
    w_s = 282.9404 + 4.70935e-5 * d
    M_s = rev(356.0470 + 0.9856002585 * d)
    L_s = rev(w_s + M_s)
    gmst0_hours = (L_s + 180.0) / 15.0
    gmst_hours  = gmst0_hours + ut_hours
    lst_hours   = gmst_hours + lon_east/15.0
    return rev(lst_hours * 15.0)


def _doppler(d, lat_deg, az_deg, alt_deg):
    """Topocentric range-rate (km/s) and the fractional Doppler shift it implies.

    Two contributions, summed along the line of sight - both real geometry,
    nothing fitted or invented:

      ORBITAL    : how fast the Earth-Moon distance itself is changing right
                   now. A centred numerical derivative of the geocentric
                   distance over a +/- 1 hour window - short enough that the
                   ~27-day breathing is locally linear, long enough that the
                   float subtraction isn't noise.
      ROTATIONAL : the observer's eastward speed from Earth's spin,
                   v_rot = omega_earth * R_earth * cos(latitude), projected
                   onto the line-of-sight direction to the Moon. In a local
                   East-North-Up frame the LOS unit vector is
                   (sin(az)cos(alt), cos(az)cos(alt), sin(alt)); the observer's
                   velocity is purely eastward, so the dot product collapses to
                   v_rot * sin(az) * cos(alt). Positive means the spin is
                   carrying the observer toward the Moon's bearing - closing
                   the range - so it SUBTRACTS from the rate of change of range.

    Doppler: a growing range redshifts (delta-f/f = -range_rate / c); a
    shrinking range blueshifts. An echo (radar / moonbounce / EME) crosses the
    gap twice, so its shift is double the one-way figure.
    """
    DT_DAYS = 1.0 / 24.0
    r_minus = moon_position(d - DT_DAYS)["r"]
    r_plus  = moon_position(d + DT_DAYS)["r"]
    orbital_km_s = (r_plus - r_minus) * EARTH_RADIUS_KM / (2.0 * DT_DAYS * 86400.0)

    v_rot = (2.0 * math.pi * EARTH_RADIUS_KM / SIDEREAL_DAY_S) * cos(lat_deg)
    rotational_km_s = -v_rot * sin(az_deg) * cos(alt_deg)

    range_rate_km_s = orbital_km_s + rotational_km_s
    one_way_ppb = -range_rate_km_s / LIGHT_SPEED_KM_S * 1e9
    echo_ppb = 2.0 * one_way_ppb

    return {
        "range_rate_km_s": range_rate_km_s,
        "orbital_km_s": orbital_km_s,
        "rotational_km_s": rotational_km_s,
        "shift_one_way_ppb": one_way_ppb,
        "shift_echo_ppb": echo_ppb,
    }


def moon_fix(lat_deg, lon_east_deg, when_utc=None, altitude_m=0.0):
    """Full topocentric fix: bearing, altitude, phase, and the go/hold/stop gate."""
    if when_utc is None:
        when_utc = datetime.now(timezone.utc)
    elif when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    when_utc = when_utc.astimezone(timezone.utc)

    d = day_number(when_utc)
    ut_hours = when_utc.hour + when_utc.minute/60.0 + when_utc.second/3600.0
    m = moon_position(d)
    lst = local_sidereal_time(d, lon_east_deg, ut_hours)
    ha = rev(lst - m["ra"])               # hour angle, deg (0..360)

    # geocentric alt/az (Meeus: azimuth from south, westward), then to from-north
    H = ha
    alt_geo = asin(sin(lat_deg)*sin(m["dec"]) + cos(lat_deg)*cos(m["dec"])*cos(H))
    A_south = atan2(sin(H), cos(H)*sin(lat_deg) - tan(m["dec"])*cos(lat_deg))
    az = rev(A_south + 180.0)

    # topocentric parallax in altitude (the term that decides the horizon gate)
    par = asin(1.0 / m["r"])              # horizontal parallax, deg (~0.95)
    alt = alt_geo - par*cos(alt_geo)      # parallax always lowers the Moon

    # phase / illuminated fraction
    elong = acos(cos(m["lat"])*cos(m["lon"] - m["sun_lon"]))
    illum = (1.0 - cos(elong)) / 2.0
    waxing = rev(m["lon"] - m["sun_lon"]) < 180.0

    geo_verdict, geo_reason = _gate_geometry(alt)
    lum_verdict, lum_reason = _gate_luminescent(alt, illum)
    dop = _doppler(d, lat_deg, az, alt)
    dop_verdict, dop_reason = _gate_doppler(alt, dop["range_rate_km_s"])

    return {
        "when_utc": when_utc.isoformat(timespec="seconds"),
        "lat": lat_deg, "lon_east": lon_east_deg, "altitude_m": altitude_m,
        "azimuth_deg": az, "altitude_deg": alt,
        "illum_frac": illum, "phase": _phase_name(elong, waxing),
        "distance_earth_radii": m["r"],
        "geometry": {"verdict": geo_verdict, "reason": geo_reason},
        "luminescent": {"verdict": lum_verdict, "reason": lum_reason},
        "doppler": {"verdict": dop_verdict, "reason": dop_reason, **dop},
    }


def _gate_geometry(alt):
    if alt < 0.0:
        return "STOP", f"Moon below horizon ({alt:.1f} deg). No bearing."
    if alt < HORIZON_BAND:
        return "HOLD", (f"Moon low ({alt:.1f} deg). Within the "
                        f"{HORIZON_BAND:.0f} deg horizon band where parallax+"
                        f"refraction blur the bearing ~1 deg.")
    return "GO", f"Moon clear of horizon ({alt:.1f} deg). Bearing trustworthy."


def _gate_doppler(alt, range_rate_km_s):
    """Same gate as the bearing: a clean Doppler read leans on the same az/alt
    geometry as the compass, so the same horizon-band uncertainty blurs both."""
    if alt < 0.0:
        return "STOP", "Moon below horizon. No path - nothing to shift."
    if alt < HORIZON_BAND:
        return "HOLD", (f"Moon low ({alt:.1f} deg); the same horizon-band blur "
                        f"that softens the bearing softens the rotational term.")
    return "GO", (f"Clear path; range-rate {range_rate_km_s*1000.0:+.0f} m/s "
                  f"is a clean read.")


def _gate_luminescent(alt, illum):
    if alt < 0.0:
        return "STOP", "Moon below horizon. No light reaching the sensor."
    if illum < ILLUM_MIN:
        return "HOLD", (f"Moon up but nearly dark ({illum*100:.0f}% lit). "
                        f"Too little lunar light to drive the luminescent read.")
    if alt < HORIZON_BAND:
        return "HOLD", f"Moon lit ({illum*100:.0f}%) but low; light path grazes."
    return "GO", f"Moon up and lit ({illum*100:.0f}%). Luminescent read viable."


def _phase_name(elong, waxing):
    if elong < 20:    return "new"
    if elong < 70:    return "waxing crescent" if waxing else "waning crescent"
    if elong < 110:   return "first quarter" if waxing else "last quarter"
    if elong < 160:   return "waxing gibbous" if waxing else "waning gibbous"
    return "full"


def format_fix(f):
    g, l, dp = f["geometry"], f["luminescent"], f["doppler"]
    return "\n".join([
        f"  time (UTC) : {f['when_utc']}",
        f"  position   : lat {f['lat']:.4f}, lon {f['lon_east']:.4f}"
        + (f", alt {f['altitude_m']:.0f} m" if f['altitude_m'] else ""),
        "",
        f"  MOON BEARING : {f['azimuth_deg']:6.1f} deg   ({_compass_point(f['azimuth_deg'])})",
        f"  altitude     : {f['altitude_deg']:6.1f} deg   "
        + ("(above horizon)" if f['altitude_deg'] >= 0 else "(below horizon)"),
        f"  phase        : {f['phase']}  ({f['illum_frac']*100:.0f}% lit)",
        f"  range-rate   : {dp['range_rate_km_s']*1000:+6.0f} m/s   "
        + ("(receding -> redshift)" if dp['range_rate_km_s'] >= 0 else "(approaching -> blueshift)"),
        f"  Doppler      : {dp['shift_one_way_ppb']:+7.1f} ppb one-way   "
        f"{dp['shift_echo_ppb']:+7.1f} ppb echo (radar/EME)",
        "",
        f"  COMPASS  (geometry)    : {g['verdict']:4}  {g['reason']}",
        f"  LIGHT    (luminescent) : {l['verdict']:4}  {l['reason']}",
        f"  DOPPLER  (range-rate)  : {dp['verdict']:4}  {dp['reason']}",
    ])


def _compass_point(az):
    pts = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return pts[int((az + 11.25) % 360 / 22.5)]


# ---- self-test: audit the method before trusting a fix ---------------------
def _illum_only(d):
    m = moon_position(d)
    elong = acos(cos(m["lat"])*cos(m["lon"] - m["sun_lon"]))
    return (1.0 - cos(elong)) / 2.0


def _self_test():
    print("moon_lines self-test - auditing the method\n")
    ok = True

    # 1) Moon's ecliptic longitude must advance ~12-14 deg/day (mean 13.18).
    d0 = day_number(datetime(2026, 6, 8, 0, 0, 0, tzinfo=timezone.utc))
    advances = []
    for k in range(10):
        l1 = moon_position(d0 + k)["lon"]
        l2 = moon_position(d0 + k + 1)["lon"]
        advances.append((l2 - l1) % 360.0)
    lo, hi = min(advances), max(advances)
    passed = 11.0 <= lo and hi <= 15.5
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] daily longitude advance "
          f"{lo:.2f}-{hi:.2f} deg/day (expect ~12-14, mean 13.18)")

    # 2) Illuminated fraction must stay in [0,1] across a lunation.
    bad = [k for k in range(30) if not (0.0 <= _illum_only(d0 + k) <= 1.0)]
    passed = not bad
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] illuminated fraction in [0,1] over 30 days")

    # 3) Over a day the Moon rises and sets: altitude must take both signs.
    alts = [moon_fix(40.90, -80.86,
            datetime(2026,6,8,h,0,0,tzinfo=timezone.utc))["altitude_deg"]
            for h in range(24)]
    passed = max(alts) > 0 and min(alts) < 0
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] altitude crosses horizon over 24 h "
          f"(max {max(alts):.0f}, min {min(alts):.0f})")

    # 4) Azimuth always in [0,360), altitude in [-90,90].
    f = moon_fix(40.90, -80.86, datetime(2026,6,8,3,0,0,tzinfo=timezone.utc))
    passed = (0 <= f["azimuth_deg"] < 360) and (-90 <= f["altitude_deg"] <= 90)
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] bearing/altitude in range "
          f"(az {f['azimuth_deg']:.0f}, alt {f['altitude_deg']:.0f})")

    # 5) Gate consistency: below-horizon must force ALL THREE channels to STOP.
    fixes = [moon_fix(40.90, -80.86, datetime(2026,6,8,h,0,0,tzinfo=timezone.utc))
             for h in range(24)]
    consistent = all(
        not (ff["geometry"]["verdict"] == "STOP"
             and (ff["luminescent"]["verdict"] != "STOP" or ff["doppler"]["verdict"] != "STOP"))
        for ff in fixes)
    ok &= consistent
    print(f"[{'PASS' if consistent else 'FAIL'}] below-horizon forces all three gates to STOP")

    # 6) Range-rate must sit inside its physical envelope: orbital breathing
    #    (a few tens of m/s, from the ~27-day perigee/apogee cycle) plus the
    #    rotational term, which can be no larger than Earth's own spin speed
    #    (omega_earth * R_earth =~ 0.46 km/s at the equator, less elsewhere).
    #    A bug that mixed up units or dropped the cos(lat) would blow past this.
    rates = [ff["doppler"]["range_rate_km_s"] for ff in fixes]
    envelope = (2*math.pi*EARTH_RADIUS_KM/SIDEREAL_DAY_S) + 0.1
    passed = all(abs(rt) < envelope for rt in rates)
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] range-rate within physical envelope "
          f"(|rate| max {max(abs(rt) for rt in rates)*1000:.0f} m/s, "
          f"envelope {envelope*1000:.0f} m/s)")

    # 7) The rotational term must change sign over a day: the Moon crosses from
    #    one side of the sky to the other, and Earth's spin carries the observer
    #    toward it on one side and away on the other. A real geometric quantity
    #    flips; a constant bias would mean sin(az) (or the sign convention) is
    #    wrong. Same falsifiability spirit as the horizon-crossing check above.
    rotational = [ff["doppler"]["rotational_km_s"] for ff in fixes]
    passed = max(rotational) > 0 and min(rotational) < 0
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] rotational Doppler term changes sign over 24 h "
          f"(max {max(rotational)*1000:+.0f}, min {min(rotational)*1000:+.0f} m/s)")

    print("\n" + ("ALL PASS - method is sound; feed it a real position."
                   if ok else "FAIL - do not trust fixes until this passes."))
    print("\nExample live-shaped fix (Salem, OH, now):")
    print(format_fix(moon_fix(40.9006, -80.8568)))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        _self_test()
    else:
        lat = float(sys.argv[1]); lon = float(sys.argv[2])
        alt = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
        print(format_fix(moon_fix(lat, lon, altitude_m=alt)))
