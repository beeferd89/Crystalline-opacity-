#!/usr/bin/env python3
"""
tidal_lines.py - does a groundwater series contain the tidal lines?
Kibler AI Solutions Corp.

ONE QUESTION, FALSIFIABLE:
  Does a water-level time series carry M2 (12.421h) and S2 (12.000h) as SHARP
  spectral lines standing above the local background? If yes, the well is
  tidally coupled and can serve as the forcing reference (the clock). If no,
  it is too damped / too shallow / too coarsely sampled - learned cleanly,
  before anything is built on it.

WHY SHARP-LINE, NOT JUST "POWER AT M2":
  Verified earlier the hard way: a slow drift near ~12-13h FAKES power at M2 at
  short records. A real tidal constituent is a NARROW line; broadband noise and
  drift are WIDE. So the test is power AT the constituent / median power in a
  neighbourhood band that EXCLUDES the constituents. A real line stands up; a
  drift bump does not.

WHAT THIS FILE DOES:
  1. Pure functions: detrend, periodogram power at a period, sharp-line ratio.
  2. analyze(times_hours, values) -> verdict per constituent + report.
  3. parse_usgs_iv(json) -> (times_hours, values) from a USGS Instantaneous
     Values response, so the real pull drops straight in.
  4. A synthetic self-test (run with no args) that PROVES the discriminator
     before any real data touches it: clean tidal -> LOCK, noise -> no,
     near-M2 drift -> correctly rejected at adequate record length.

NO network here. The Mac does the fetch; this does the math.
Usage:
  python3 tidal_lines.py                 # synthetic self-test (audit the method)
  python3 tidal_lines.py path/usgs.json  # analyze a saved USGS IV json
"""

import sys, json, math

# Principal tidal constituents, periods in hours
CONSTITUENTS = {
    "M2": 12.4206,   # principal lunar semidiurnal  -- the lunar line
    "S2": 12.0000,   # principal solar semidiurnal
    "N2": 12.6583,   # larger lunar elliptic
    "K1": 23.9345,   # lunar diurnal
    "O1": 25.8193,   # principal lunar diurnal
}
# the two that matter most for "is the moon in this signal": M2 and S2
PRIMARY = ("M2", "S2")


# ---- pure math --------------------------------------------------------------

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

def detrend(values):
    """Remove linear trend (least squares). A sloping water table is not tide;
    removing it stops the slope leaking broadband power into low frequencies."""
    n = len(values)
    if n < 3:
        return list(values)
    xm = (n - 1) / 2.0
    ym = _mean(values)
    sxx = sum((i - xm) ** 2 for i in range(n))
    sxy = sum((i - xm) * (values[i] - ym) for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    intercept = ym - slope * xm
    return [values[i] - (slope * i + intercept) for i in range(n)]

def power_at(times_h, values, period_h):
    """Normalized periodogram power at a given period.
    Lomb-style projection onto sin/cos at that frequency; handles uneven dt."""
    n = len(values)
    if n < 4 or period_h <= 0:
        return 0.0
    w = 2.0 * math.pi / period_h
    m = _mean(values)
    sr = si = var = 0.0
    for i in range(n):
        v = values[i] - m
        a = w * times_h[i]
        sr += v * math.cos(a)
        si += v * math.sin(a)
        var += v * v
    if var <= 0:
        return 0.0
    # power as fraction of variance explained at this frequency
    return (sr * sr + si * si) / (n * 0.5 * var)

def phase_at(times_h, values, period_h):
    """Phase (radians) of the component at period_h. For cross-channel lag."""
    n = len(values); w = 2.0 * math.pi / period_h; m = _mean(values)
    sr = si = 0.0
    for i in range(n):
        v = values[i] - m; a = w * times_h[i]
        sr += v * math.cos(a); si += v * math.sin(a)
    return math.atan2(si, sr)

def peak_period_near(times_h, values, target_h, search_h=0.7, steps=400):
    """Find the period of the actual power peak in a narrow window around a
    target constituent. THE discriminator: a real constituent peaks at its own
    exact period; a nearby drift peaks at the DRIFT period, not the target.
    Returns (peak_period_h, peak_power, offset_from_target_h)."""
    lo, hi = target_h - search_h, target_h + search_h
    best_P, best_p = target_h, -1.0
    for s in range(steps + 1):
        P = lo + (hi - lo) * s / steps
        p = power_at(times_h, values, P)
        if p > best_p:
            best_p, best_P = p, P
    return best_P, best_p, abs(best_P - target_h)


def sharp_line_ratio(times_h, values, period_h, band=(9.0, 30.0), exclude_h=0.30):
    """The discriminator: power AT period_h divided by the MEDIAN power across a
    neighbourhood band, EXCLUDING bins near any known constituent. A narrow real
    line >> background -> high ratio. A broad drift bump -> ratio near 1."""
    p0 = power_at(times_h, values, period_h)
    bg = []
    steps = 120
    lo, hi = band
    for s in range(steps + 1):
        P = lo * math.pow(hi / lo, s / steps)
        # skip bins close to ANY constituent so lines don't inflate the background
        if any(abs(P - c) < exclude_h for c in CONSTITUENTS.values()):
            continue
        bg.append(power_at(times_h, values, P))
    if not bg:
        return 0.0
    bg.sort()
    med = bg[len(bg) // 2]
    return p0 / med if med > 1e-12 else 0.0


# ---- verdict ----------------------------------------------------------------

def _record_hours(times_h):
    return (max(times_h) - min(times_h)) if len(times_h) > 1 else 0.0

def analyze(times_h, values, constituents=PRIMARY):
    """Full verdict. Returns a dict: per-constituent ratio + lock verdict,
    plus record length and the resolution caveat (M2 vs S2 need ~long records)."""
    if len(values) < 24:
        return {"error": f"too few samples ({len(values)}) - need a longer record"}
    v = detrend(values)
    rec_h = _record_hours(times_h)
    rec_days = rec_h / 24.0

    # Rayleigh resolution: can we separate M2 from S2? need T > 1/|f_M2 - f_S2|
    df = abs(1/CONSTITUENTS["M2"] - 1/CONSTITUENTS["S2"])
    res_days = (1.0 / df) / 24.0  # ~14.8 days to split M2/S2

    out = {
        "record_days": round(rec_days, 1),
        "samples": len(values),
        "m2_s2_resolvable": rec_days >= res_days,
        "resolution_needed_days": round(res_days, 1),
        "constituents": {},
    }
    for name in constituents:
        P = CONSTITUENTS[name]
        ratio = sharp_line_ratio(times_h, v, P)
        peak_P, peak_pw, offset = peak_period_near(times_h, v, P)
        # Resolution-aware tolerance: the longer the record, the tighter we can
        # localize the peak. Below the M2/S2 resolution length, loosen it.
        tol = 0.12 if rec_days >= res_days else 0.25
        line_ok = ratio > 6.0
        peak_ok = offset <= tol
        # BOTH must hold: a strong line AND the peak sitting at THIS period,
        # not at a neighbouring drift frequency. This is what defeats the trap.
        if line_ok and peak_ok:
            verdict = "LINE PRESENT"
        elif line_ok and not peak_ok:
            verdict = f"peak off-target ({peak_P:.2f}h) - likely drift, not {name}"
        elif ratio > 3.0 and peak_ok:
            verdict = "marginal"
        else:
            verdict = "absent"
        out["constituents"][name] = {
            "period_h": P,
            "sharp_line_ratio": round(ratio, 2),
            "peak_period_h": round(peak_P, 3),
            "peak_offset_h": round(offset, 3),
            "verdict": verdict,
            "phase_rad": round(phase_at(times_h, v, P), 4),
        }

    m2 = out["constituents"].get("M2", {})
    present = [n for n, c in out["constituents"].items() if c["verdict"] == "LINE PRESENT"]
    if "M2" in present:
        out["overall"] = "TIDALLY COUPLED - usable as forcing reference"
    elif present:
        out["overall"] = f"partial - {','.join(present)} present, M2 not clear"
    elif any(c["verdict"] == "marginal" for c in out["constituents"].values()):
        out["overall"] = "marginal - longer record may resolve it"
    else:
        out["overall"] = "NO TIDAL LINES - wrong well, too damped, or too coarse"
    if not out["m2_s2_resolvable"]:
        out["caveat"] = (f"record {rec_days:.1f}d < {res_days:.1f}d needed to fully "
                         f"separate M2 from S2 - treat a lone lock as provisional")
    return out


# ---- USGS parsing -----------------------------------------------------------

def parse_usgs_iv(obj):
    """Parse a USGS Instantaneous Values (IV) JSON into (times_hours, values).
    Water level param codes: 72019 (depth to water below surface) or
    62611 (groundwater level above datum). Streamflow 00060, gage height 00065.
    Picks the first timeseries with numeric values. Times -> hours from first.
    """
    try:
        series = obj["value"]["timeSeries"]
    except (KeyError, TypeError):
        raise ValueError("not a USGS IV response (missing value.timeSeries)")
    for ts in series:
        pts = ts["values"][0]["value"]
        times, vals = [], []
        for p in pts:
            try:
                val = float(p["value"])
            except (TypeError, ValueError):
                continue
            if val <= -999999:   # USGS no-data sentinel
                continue
            # dateTime like '2026-05-30T06:10:00.000-04:00'
            times.append(p["dateTime"])
            vals.append(val)
        if len(vals) >= 24:
            t0 = _iso_to_epoch(times[0])
            th = [(_iso_to_epoch(t) - t0) / 3600.0 for t in times]
            var = ts["variable"]["variableName"]
            return th, vals, var
    raise ValueError("no timeseries with >=24 numeric points found")

def _iso_to_epoch(s):
    """Minimal ISO8601 -> epoch seconds, tolerant of timezone offset & millis."""
    import datetime
    s = s.strip()
    # python 3.11+ handles most of this; normalize 'Z'
    s = s.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError:
        # strip fractional seconds if present in an odd format
        if "." in s:
            head, _, tail = s.partition(".")
            tz = ""
            for i, ch in enumerate(tail):
                if ch in "+-":
                    tz = tail[i:]; break
            return datetime.datetime.fromisoformat(head + tz).timestamp()
        raise


# ---- synthetic self-test (audit the method before real data) ----------------

def _synth(days, dt_min, amp_m2, amp_s2, noise, drift_amp, drift_period=12.7, seed=1):
    import random
    rng = random.Random(seed)
    n = int(days * 24 * 60 / dt_min)
    th, vals = [], []
    ph_m2, ph_s2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    dw = 0.0
    for i in range(n):
        t = i * dt_min / 60.0
        x = (amp_m2 * math.cos(2*math.pi*t/12.4206 + ph_m2)
             + amp_s2 * math.cos(2*math.pi*t/12.0 + ph_s2))
        dw += rng.gauss(0, 1) * 0.02
        x += drift_amp * (math.cos(2*math.pi*t/drift_period + 0.7) + 0.4*dw)
        x += noise * rng.gauss(0, 1)
        th.append(t); vals.append(x)
    return th, vals

def self_test():
    print("SELF-TEST — auditing the discriminator before real data\n")
    cases = [
        ("A real tide (M2+S2), light noise   ", dict(days=21, dt_min=15, amp_m2=1.0, amp_s2=0.46, noise=0.4, drift_amp=0.05)),
        ("B noise only, no tide              ", dict(days=21, dt_min=15, amp_m2=0.0, amp_s2=0.0, noise=1.0, drift_amp=0.0)),
        ("C near-M2 drift only, NO tide      ", dict(days=21, dt_min=15, amp_m2=0.0, amp_s2=0.0, noise=0.3, drift_amp=1.0)),
        ("D weak tide, heavy noise           ", dict(days=21, dt_min=15, amp_m2=0.35, amp_s2=0.16, noise=1.0, drift_amp=0.1)),
        ("E real tide + heavy near-M2 drift  ", dict(days=28, dt_min=15, amp_m2=1.0, amp_s2=0.46, noise=0.4, drift_amp=0.9)),
        ("F short record real tide (5 days)  ", dict(days=5,  dt_min=15, amp_m2=1.0, amp_s2=0.46, noise=0.4, drift_amp=0.05)),
    ]
    for label, kw in cases:
        th, vals = _synth(**kw)
        r = analyze(th, vals)
        m2 = r["constituents"]["M2"]; s2 = r["constituents"]["S2"]
        print(f"{label} | M2 ratio={m2['sharp_line_ratio']:7.2f} ({m2['verdict']:>12}) "
              f"S2={s2['sharp_line_ratio']:6.2f} | {r['record_days']}d | {r['overall']}")
    print("\nExpected: A LINE, B absent, C absent(drift rejected), D marginal/LINE,")
    print("E LINE (tide survives drift), F LINE-but-caveated (short record).")
    print("If C reads absent, the drift trap is correctly defeated by the sharp-line test.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            obj = json.load(f)
        th, vals, var = parse_usgs_iv(obj)
        print(f"parsed: {len(vals)} points, variable = {var}")
        result = analyze(th, vals)
        print(json.dumps(result, indent=2))
    else:
        self_test()
