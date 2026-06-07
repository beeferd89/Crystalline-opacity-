#!/usr/bin/env python3
"""
spectro_core.py - a domain-agnostic spectrometer kernel
Kibler AI Solutions Corp.

ONE ENGINE, MANY SPECTRA:
  tidal_lines.py proved the kernel: find NARROW lines standing above a local
  background, at KNOWN catalog positions, with a real significance test. That is
  exactly what a spectrometer does. This file lifts that kernel out of the tidal
  domain so the SAME engine reads any line spectrum - you swap three plugs:

    1. CATALOG   - which lines to look for (tides / XRF elements / isotopes /
                   optical / audio). One domain at a time, interchangeable.
    2. SPECTRUM  - a continuous SampledSignal (uneven time series -> Lomb-Scargle)
                   OR a BinnedSpectrum (counts vs energy -> Poisson statistics).
                   The significance test matches the physics of the data.
    3. FRONT-END - one channel, a multi-channel array, or a 2-D imaging grid.
                   Hardware feeds software through ONE contract (IngestSource);
                   this file imports NO hardware library.

REPEATABLE: every report carries a sha256 digest of (catalog + data + options),
  so any run is independently recomputable - the recomputation ethos of
  portability_layer.py, applied to measurement.

The validated tidal estimators are IMPORTED, not copied. tidal_lines.py stays the
reference; the tides catalog reproduces it line for line (see self_test).

NO network, NO hardware here. Usage:
  python3 spectro_core.py        # synthetic self-test across domains
"""

import sys, json, math, hashlib, random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Union, Protocol, runtime_checkable

# Validated, catalog-INDEPENDENT estimators - reused, not reimplemented.
from tidal_lines import (
    detrend, power_at, phase_at, false_alarm_prob, CONSTITUENTS,
)


# ============================================================================
# 1. CATALOG LAYER  - pure data, the swappable "what to look for"
# ============================================================================

@dataclass(frozen=True)
class Line:
    name: str            # "Fe-Ka", "M2", "Cs137"
    position: float      # keV, or period-in-hours, or Hz - units per catalog
    weight: float = 1.0  # relative intensity hint (Kb < Ka etc.); advisory only
    group: str = ""      # optional grouping ("Fe", "Cu", "Co-60")

@dataclass(frozen=True)
class LineCatalog:
    domain: str               # "tides" | "xrf" | "gamma" | "optical" | ...
    unit: str                 # "hour" | "keV" | "nm" | "Hz"
    axis_is_period: bool      # True: axis is PERIOD (tides). False: energy/freq.
    lines: Tuple[Line, ...]
    primary: Tuple[str, ...] = ()   # names that drive the "overall" verdict

    def positions(self) -> List[float]:
        return [ln.position for ln in self.lines]

    def by_name(self) -> Dict[str, Line]:
        return {ln.name: ln for ln in self.lines}

    def targets(self) -> Tuple[str, ...]:
        # what we REPORT on; exclusion/background always uses ALL lines.
        return self.primary if self.primary else tuple(ln.name for ln in self.lines)

    def digest(self) -> str:
        body = json.dumps(
            sorted((ln.name, round(ln.position, 6), ln.weight) for ln in self.lines),
            sort_keys=True)
        return hashlib.sha256((self.domain + "|" + body).encode()).hexdigest()


def make_catalog(domain, unit, axis_is_period, lines, primary=()):
    """Build an ad-hoc catalog. `lines` is an iterable of (name, position[, weight
    [, group]]) tuples or Line objects. For optical/audio/general, fill your own."""
    out = []
    for ln in lines:
        out.append(ln if isinstance(ln, Line) else Line(*ln))
    return LineCatalog(domain, unit, axis_is_period, tuple(out), tuple(primary))


# ---- shipped catalogs ------------------------------------------------------

# TIDES: reuse the validated constituent table so the tidal path is identical.
TIDES = LineCatalog(
    domain="tides", unit="hour", axis_is_period=True,
    lines=tuple(Line(n, p) for n, p in CONSTITUENTS.items()),
    primary=("M2", "S2"),
)

# XRF: characteristic K-alpha1 / K-beta1 energies (keV). Pb at this range is the
# L series (flagged in the name), not K - a deliberate reminder that lines from
# different shells/elements can crowd (Pb-La 10.55 sits right by As-Ka 10.54).
XRF = make_catalog(
    "xrf", "keV", False,
    [("Ca-Ka", 3.69, 1.0, "Ca"), ("Ca-Kb", 4.01, 0.13, "Ca"),
     ("Ti-Ka", 4.51, 1.0, "Ti"), ("Ti-Kb", 4.93, 0.14, "Ti"),
     ("Cr-Ka", 5.41, 1.0, "Cr"), ("Cr-Kb", 5.95, 0.14, "Cr"),
     ("Mn-Ka", 5.90, 1.0, "Mn"), ("Mn-Kb", 6.49, 0.14, "Mn"),
     ("Fe-Ka", 6.40, 1.0, "Fe"), ("Fe-Kb", 7.06, 0.14, "Fe"),
     ("Ni-Ka", 7.48, 1.0, "Ni"), ("Ni-Kb", 8.26, 0.15, "Ni"),
     ("Cu-Ka", 8.05, 1.0, "Cu"), ("Cu-Kb", 8.90, 0.15, "Cu"),
     ("Zn-Ka", 8.64, 1.0, "Zn"), ("Zn-Kb", 9.57, 0.15, "Zn"),
     ("Pb-La", 10.55, 1.0, "Pb"), ("Pb-Lb", 12.61, 0.6, "Pb"),
     ("Sr-Ka", 14.16, 1.0, "Sr"), ("Sr-Kb", 15.84, 0.15, "Sr")],
    primary=("Ca-Ka", "Ti-Ka", "Cr-Ka", "Mn-Ka", "Fe-Ka",
             "Ni-Ka", "Cu-Ka", "Zn-Ka", "Pb-La", "Sr-Ka"),
)

# GAMMA: common full-energy peaks (keV) for isotope ID / detector calibration.
GAMMA = make_catalog(
    "gamma", "keV", False,
    [("Am241", 59.54, 1.0, "Am-241"),
     ("Co57", 122.06, 1.0, "Co-57"), ("Co57b", 136.47, 0.11, "Co-57"),
     ("Na22-511", 511.0, 1.0, "Na-22"), ("Na22-1275", 1274.5, 1.0, "Na-22"),
     ("Cs137", 661.66, 1.0, "Cs-137"),
     ("Co60a", 1173.2, 1.0, "Co-60"), ("Co60b", 1332.5, 1.0, "Co-60"),
     ("K40", 1460.8, 1.0, "K-40")],
    primary=("Am241", "Cs137", "Co60a", "Co60b", "K40", "Na22-511"),
)

# Empty-but-typed: the holes are left open on purpose (author fills them).
OPTICAL = LineCatalog("optical", "nm", False, tuple())
AUDIO = LineCatalog("audio", "Hz", False, tuple())

CATALOGS: Dict[str, LineCatalog] = {
    "tides": TIDES, "xrf": XRF, "gamma": GAMMA, "optical": OPTICAL, "audio": AUDIO,
}

def get_catalog(name) -> LineCatalog:
    if name not in CATALOGS:
        raise KeyError(f"unknown catalog '{name}'; have {sorted(CATALOGS)}")
    return CATALOGS[name]


# ============================================================================
# 2. SPECTRUM KINDS
# ============================================================================

@dataclass(frozen=True)
class SampledSignal:
    """Continuous signal, possibly UNEVENLY sampled (gaps/jitter ok)."""
    times: Tuple[float, ...]    # in the catalog's axis-driving unit (e.g. hours)
    values: Tuple[float, ...]

@dataclass(frozen=True)
class BinnedSpectrum:
    """Already-binned counts vs position (e.g. counts vs energy in keV)."""
    centers: Tuple[float, ...]  # bin centers, ascending
    counts: Tuple[float, ...]   # raw counts (Poisson statistics)


# ============================================================================
# Poisson statistics for counting data (pure Python, no numpy/scipy)
#   Regularized incomplete gamma via Numerical-Recipes series + continued frac.
# ============================================================================

def _gser(a, x, itmax=300, eps=1e-14):
    if x <= 0:
        return 0.0
    ap = a; s = 1.0 / a; d = s
    for _ in range(itmax):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * eps:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))

def _gcf(a, x, itmax=300, eps=1e-14, tiny=1e-300):
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, itmax):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h

def gammp(a, x):
    """Regularized lower incomplete gamma P(a, x)."""
    if x < 0 or a <= 0:
        raise ValueError("gammp domain")
    if x == 0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)

def poisson_sf(k, lam):
    """P(X >= k | mean=lam) for a Poisson process. The chance background alone
    matched-or-beat an observed count. Identity: P(X>=k) = gammp(k, lam)."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    return gammp(float(k), float(lam))


# ============================================================================
# Generic catalog-dependent geometry (ports of the tidal logic, parameterized
# by an arbitrary set of line positions instead of the global CONSTITUENTS).
# ============================================================================

def _voronoi_cell(positions, target, search):
    """Half-way points to the nearest line below and above `target`, capped by
    `search`. Keeps each line's peak search inside its own lane."""
    below = [c for c in positions if c < target - 1e-9]
    above = [c for c in positions if c > target + 1e-9]
    lo = target - search
    hi = target + search
    if below:
        lo = max(lo, (target + max(below)) / 2.0)
    if above:
        hi = min(hi, (target + min(above)) / 2.0)
    return lo, hi

def peak_near_generic(times, values, target, positions, search=0.5, steps=400):
    """Interior-peak discriminator (see tidal_lines.peak_period_near): a real
    line shows an INTERIOR maximum at its position; drift / neighbour leakage
    shows a shoulder pinned to the Voronoi cell edge -> reported far off-target.
    Returns (peak_position, peak_power, offset)."""
    lo, hi = _voronoi_cell(positions, target, search)
    best_s, best_P, best_p = -1, target, -1.0
    for s in range(steps + 1):
        P = lo + (hi - lo) * s / steps
        p = power_at(times, values, P)
        if p > best_p:
            best_p, best_P, best_s = p, P, s
    if best_s == 0 or best_s == steps:
        return best_P, best_p, search + 1.0
    return best_P, best_p, abs(best_P - target)

def local_snr_generic(times, values, target, positions,
                      half_width=3.0, exclude=0.30):
    """Power AT target / median power in a LOCAL neighbourhood, excluding bins
    near ANY catalog line. Local => robust to a red-noise floor tilt. Mirrors
    tidal_lines.sharp_line_ratio with the constituent set passed in."""
    p0 = power_at(times, values, target)
    bg = []
    steps = 100
    lo = max(target - half_width, 1e-9)
    hi = target + half_width
    for s in range(steps + 1):
        P = lo + (hi - lo) * s / steps
        if any(abs(P - c) < exclude for c in positions):
            continue
        bg.append(power_at(times, values, P))
    if not bg:
        return 0.0
    bg.sort()
    med = bg[len(bg) // 2]
    return p0 / med if med > 1e-12 else 0.0


# ============================================================================
# Unified report types
# ============================================================================

@dataclass
class LineResult:
    name: str
    position: float
    statistic: float        # local-SNR ratio (sampled) OR sigma (binned)
    p_value: float          # Lomb-Scargle FAP (sampled) OR Poisson tail (binned)
    peak_position: float
    peak_offset: float
    verdict: str
    extra: Dict = field(default_factory=dict)

@dataclass
class SpectrumReport:
    domain: str
    kind: str               # "sampled" | "binned"
    lines: Dict[str, LineResult]
    overall: str
    meta: Dict
    digest: str
    caveat: str = ""

    def as_dict(self):
        return {
            "domain": self.domain, "kind": self.kind, "overall": self.overall,
            "meta": self.meta, "caveat": self.caveat, "digest": self.digest[:24] + "...",
            "lines": {n: {
                "position": r.position, "statistic": round(r.statistic, 3),
                "p_value": float(f"{r.p_value:.2e}"),
                "peak_position": round(r.peak_position, 4),
                "peak_offset": round(r.peak_offset, 4),
                "verdict": r.verdict, **r.extra,
            } for n, r in self.lines.items()},
        }


def _digest(catalog, data_arrays, options):
    payload = {
        "catalog": catalog.digest(),
        "data": [[round(x, 6) for x in arr] for arr in data_arrays],
        "options": {k: options[k] for k in sorted(options)},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _overall(catalog, lines):
    present = [n for n, r in lines.items() if r.verdict == "LINE PRESENT"]
    prim = [p for p in catalog.primary if p in present]
    if catalog.primary and prim and len(prim) == len([p for p in catalog.primary if p in lines]):
        return f"ALL PRIMARY LINES PRESENT ({','.join(prim)})"
    if prim:
        return f"PARTIAL - primary present: {','.join(prim)}"
    if present:
        return f"SECONDARY LINES ONLY: {','.join(present)}"
    if any(r.verdict == "marginal" for r in lines.values()):
        return "MARGINAL - longer/cleaner record may resolve it"
    return "NO LINES DETECTED"


# ============================================================================
# 2a. Continuous path - Lomb-Scargle (reuses tidal estimators)
# ============================================================================

def analyze_sampled(signal: SampledSignal, catalog: LineCatalog,
                    options: Optional[Dict] = None) -> SpectrumReport:
    options = dict(options or {})
    times, raw = list(signal.times), list(signal.values)
    if len(raw) < 24:
        return SpectrumReport(catalog.domain, "sampled", {},
                              f"too few samples ({len(raw)})", {}, "")
    v = detrend(raw, times)
    positions = catalog.positions()
    rec = (max(times) - min(times)) if len(times) > 1 else 0.0
    n_indep = max(1.0, -6.362 + 1.193 * len(v) + 0.00098 * len(v) * len(v))

    # Rayleigh-style resolution from the two CLOSEST lines (in frequency).
    resolvable, res_needed = True, 0.0
    freqs = sorted((1.0 / p) if catalog.axis_is_period else p for p in positions)
    if len(freqs) >= 2:
        df = min(b - a for a, b in zip(freqs, freqs[1:]) if b > a)
        if df > 0:
            res_needed = 1.0 / df
            resolvable = rec >= res_needed

    lines = {}
    for name in catalog.targets():
        P = catalog.by_name()[name].position
        ratio = local_snr_generic(times, v, P, positions)
        peak_P, _, offset = peak_near_generic(times, v, P, positions)
        fap = false_alarm_prob(times, v, P, n_indep)
        tol = 0.12 if resolvable else 0.25
        line_ok, peak_ok, sig_ok = ratio > 6.0, offset <= tol, fap < 0.01
        if line_ok and peak_ok and sig_ok:
            verdict = "LINE PRESENT"
        elif line_ok and sig_ok and not peak_ok:
            verdict = f"peak off-target ({peak_P:.3f}{catalog.unit}) - likely drift, not {name}"
        elif ratio > 3.0 and peak_ok and fap < 0.05:
            verdict = "marginal"
        else:
            verdict = "absent"
        lines[name] = LineResult(
            name, P, ratio, fap, peak_P, offset, verdict,
            extra={"phase_rad": round(phase_at(times, v, P), 4)})

    meta = {"record_span": round(rec, 3), "unit": catalog.unit,
            "samples": len(v), "resolvable": resolvable,
            "resolution_needed": round(res_needed, 3)}
    caveat = ("" if resolvable else
              f"span {rec:.2f}{catalog.unit} < {res_needed:.2f}{catalog.unit} needed to "
              f"separate the two closest lines - treat a lone detection as provisional")
    digest = _digest(catalog, [times, raw], options)
    return SpectrumReport(catalog.domain, "sampled", lines,
                          _overall(catalog, lines), meta, digest, caveat)


# ============================================================================
# 2b. Binned path - Poisson counting statistics
# ============================================================================

def analyze_binned(spectrum: BinnedSpectrum, catalog: LineCatalog,
                   options: Optional[Dict] = None) -> SpectrumReport:
    options = dict(options or {})
    cen, cnt = list(spectrum.centers), list(spectrum.counts)
    n = len(cen)
    if n < 8:
        return SpectrumReport(catalog.domain, "binned", {},
                              f"too few bins ({n})", {}, "")
    bw = _median([cen[i + 1] - cen[i] for i in range(n - 1)]) or 1.0
    peak_tol = options.get("peak_tol", 3.0 * bw)
    bg_hw = options.get("bg_half_width", 12.0 * bw)
    exclude = options.get("exclude", 2.0 * bw)
    sig_min = options.get("sigma_min", 5.0)      # physics 5-sigma convention
    marg_min = options.get("sigma_marginal", 3.0)
    fap_strong = options.get("fap_strong", 1e-6)
    fap_marg = options.get("fap_marginal", 1e-3)
    positions = catalog.positions()
    lo_E, hi_E = cen[0], cen[-1]

    lines = {}
    for name in catalog.targets():
        E = catalog.by_name()[name].position
        if E < lo_E - peak_tol or E > hi_E + peak_tol:
            lines[name] = LineResult(name, E, 0.0, 1.0, E, 0.0, "out of range")
            continue
        # peak = max count within +/- peak_tol of the line energy
        region = [(cen[i], cnt[i]) for i in range(n) if abs(cen[i] - E) <= peak_tol]
        gross_x, gross = max(region, key=lambda t: t[1])
        offset = abs(gross_x - E)
        # local background: per-bin median over side-bands, excluding line cores
        bg = [cnt[i] for i in range(n)
              if abs(cen[i] - E) <= bg_hw and abs(cen[i] - E) > peak_tol
              and not any(abs(cen[i] - c) < exclude for c in positions)]
        b = _median(bg) if bg else 0.0
        net = gross - b
        sigma = net / math.sqrt(b) if b > 0 else (net / math.sqrt(max(gross, 1.0)))
        pval = poisson_sf(int(round(gross)), b) if b > 0 else (0.0 if net > 0 else 1.0)
        on_target = offset <= peak_tol
        if sigma >= sig_min and on_target and pval < fap_strong:
            verdict = "LINE PRESENT"
        elif sigma >= sig_min and pval < fap_strong and not on_target:
            verdict = f"peak off-target ({gross_x:.2f}{catalog.unit})"
        elif sigma >= marg_min and on_target and pval < fap_marg:
            verdict = "marginal"
        else:
            verdict = "absent"
        lines[name] = LineResult(
            name, E, sigma, pval, gross_x, offset, verdict,
            extra={"gross": round(gross, 1), "background": round(b, 2),
                   "net": round(net, 1)})

    live = sum(1 for c in cnt if c > 0)
    meta = {"unit": catalog.unit, "bins": n, "bin_width": round(bw, 4),
            "live_bins": live, "total_counts": round(sum(cnt), 1)}
    digest = _digest(catalog, [cen, cnt], options)
    return SpectrumReport(catalog.domain, "binned", lines,
                          _overall(catalog, lines), meta, digest)


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])


# ============================================================================
# 3. FRONT-END LAYER - one channel, an array, or a 2-D image.
#    Hardware feeds software through IngestSource; core imports no hardware lib.
# ============================================================================

@runtime_checkable
class IngestSource(Protocol):
    """The hardware->software contract. A driver (MCU/SDR/ADC/scintillator
    readout) implements read_spectrum() returning a SampledSignal or a
    BinnedSpectrum. This core only CALLS it; it never imports a device library."""
    def read_spectrum(self) -> Union[SampledSignal, BinnedSpectrum]: ...


Spectrumish = Union[SampledSignal, BinnedSpectrum, IngestSource]

def _as_spectrum(x) -> Union[SampledSignal, BinnedSpectrum]:
    if isinstance(x, (SampledSignal, BinnedSpectrum)):
        return x
    if hasattr(x, "read_spectrum"):
        return x.read_spectrum()
    raise TypeError(f"not a spectrum or IngestSource: {type(x)}")

def analyze_spectrum(source: Spectrumish, catalog: LineCatalog,
                     options: Optional[Dict] = None) -> SpectrumReport:
    """Single channel. Dispatches on spectrum kind to the right significance test."""
    spec = _as_spectrum(source)
    if isinstance(spec, SampledSignal):
        return analyze_sampled(spec, catalog, options)
    return analyze_binned(spec, catalog, options)


@dataclass
class ArrayReport:
    channels: List[SpectrumReport]
    consensus: Dict[str, Dict]      # per line: how many channels see it
    digest: str

def analyze_array(sources: List[Spectrumish], catalog: LineCatalog,
                  options: Optional[Dict] = None) -> ArrayReport:
    """Multi-channel detector array: one report per channel + a per-line consensus
    (in how many channels each line reads LINE PRESENT)."""
    reps = [analyze_spectrum(s, catalog, options) for s in sources]
    consensus = {}
    for name in catalog.targets():
        present = sum(1 for r in reps if name in r.lines
                      and r.lines[name].verdict == "LINE PRESENT")
        consensus[name] = {"present_in": present, "of": len(reps)}
    digest = hashlib.sha256(
        ("|".join(r.digest for r in reps)).encode()).hexdigest()
    return ArrayReport(reps, consensus, digest)


@dataclass
class ImageReport:
    shape: Tuple[int, int]
    pixels: List[List[SpectrumReport]]
    line_maps: Dict[str, List[List[float]]]   # per-line statistic as a 2-D grid
    digest: str

def analyze_image(grid: List[List[Spectrumish]], catalog: LineCatalog,
                  options: Optional[Dict] = None) -> ImageReport:
    """2-D imaging detector: each pixel carries a spectrum. Produces a per-line
    statistic map (the spatial distribution of each line's strength)."""
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    pixels = [[analyze_spectrum(grid[r][c], catalog, options) for c in range(cols)]
              for r in range(rows)]
    line_maps = {}
    for name in catalog.targets():
        line_maps[name] = [[(pixels[r][c].lines[name].statistic
                             if name in pixels[r][c].lines else 0.0)
                            for c in range(cols)] for r in range(rows)]
    digest = hashlib.sha256(
        ("|".join(p.digest for row in pixels for p in row)).encode()).hexdigest()
    return ImageReport((rows, cols), pixels, line_maps, digest)


# ============================================================================
# Synthetic self-test (no network, no hardware) - audit each domain.
# ============================================================================

def _poisson_draw(rng, lam):
    if lam <= 0:
        return 0
    if lam < 30:                      # Knuth
        L = math.exp(-lam); k = 0; p = 1.0
        while True:
            k += 1; p *= rng.random()
            if p <= L:
                return k - 1
    return max(0, int(round(lam + math.sqrt(lam) * rng.gauss(0, 1))))

def _synth_binned(lo, hi, bw, peaks, background, seed=1):
    """peaks: list of (energy, peak_amplitude_counts, sigma_keV)."""
    rng = random.Random(seed)
    n = int(round((hi - lo) / bw))
    cen, cnt = [], []
    for i in range(n):
        E = lo + (i + 0.5) * bw
        mean = float(background)
        for (e0, amp, sig) in peaks:
            mean += amp * math.exp(-0.5 * ((E - e0) / sig) ** 2)
        cen.append(E); cnt.append(_poisson_draw(rng, mean))
    return BinnedSpectrum(tuple(cen), tuple(cnt))

def _synth_tide(days=21, dt_min=15, amp_m2=1.0, amp_s2=0.46, noise=0.4, seed=1):
    rng = random.Random(seed)
    n = int(days * 24 * 60 / dt_min)
    th, vals = [], []
    pm, ps = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    for i in range(n):
        t = i * dt_min / 60.0
        x = amp_m2 * math.cos(2*math.pi*t/12.4206 + pm) + amp_s2 * math.cos(2*math.pi*t/12.0 + ps)
        x += noise * rng.gauss(0, 1)
        th.append(t); vals.append(x)
    return SampledSignal(tuple(th), tuple(vals))


def self_test():
    print("SPECTRO-CORE SELF-TEST - one engine, many spectra\n")

    # --- XRF: Fe + Cu present, Zn injected? no -> must be rejected ---
    spec = _synth_binned(2.0, 16.0, 0.02,
                         peaks=[(6.40, 900, 0.10), (8.05, 700, 0.11)],
                         background=40, seed=7)
    r = analyze_spectrum(spec, XRF)
    fe, cu, zn = r.lines["Fe-Ka"], r.lines["Cu-Ka"], r.lines["Zn-Ka"]
    print("XRF  Fe+Cu over background:")
    print(f"   Fe-Ka  sigma={fe.statistic:7.1f}  p={fe.p_value:.1e}  {fe.verdict}")
    print(f"   Cu-Ka  sigma={cu.statistic:7.1f}  p={cu.p_value:.1e}  {cu.verdict}")
    print(f"   Zn-Ka  sigma={zn.statistic:7.1f}  p={zn.p_value:.1e}  {zn.verdict}   (not injected)")
    assert fe.verdict == "LINE PRESENT" and cu.verdict == "LINE PRESENT"
    assert zn.verdict == "absent"

    # --- GAMMA: Cs-137 present, Co-60 absent ---
    spec = _synth_binned(40.0, 1500.0, 2.0,
                         peaks=[(661.66, 1200, 18.0)], background=25, seed=3)
    r = analyze_spectrum(spec, GAMMA)
    cs, co = r.lines["Cs137"], r.lines["Co60b"]
    print("\nGAMMA  Cs-137 source:")
    print(f"   Cs137  sigma={cs.statistic:7.1f}  p={cs.p_value:.1e}  {cs.verdict}")
    print(f"   Co60b  sigma={co.statistic:7.1f}  p={co.p_value:.1e}  {co.verdict}   (not present)")
    assert cs.verdict == "LINE PRESENT" and co.verdict == "absent"

    # --- ARRAY: 3 channels, 2 carry Fe, 1 is background only ---
    chans = [
        _synth_binned(5.0, 9.0, 0.02, [(6.40, 800, 0.10)], 40, seed=11),
        _synth_binned(5.0, 9.0, 0.02, [(6.40, 750, 0.10)], 40, seed=12),
        _synth_binned(5.0, 9.0, 0.02, [], 40, seed=13),
    ]
    ar = analyze_array(chans, XRF)
    print("\nARRAY  Fe-Ka across 3 channels:")
    print(f"   consensus Fe-Ka: present in {ar.consensus['Fe-Ka']['present_in']}/{ar.consensus['Fe-Ka']['of']} channels")
    assert ar.consensus["Fe-Ka"]["present_in"] == 2

    # --- TIDES: same engine, continuous path, consistent with tidal_lines ---
    import tidal_lines as TL
    sig = _synth_tide()
    r = analyze_spectrum(sig, TIDES)
    ref = TL.analyze(list(sig.times), list(sig.values))
    m2, m2ref = r.lines["M2"], ref["constituents"]["M2"]
    print("\nTIDES  (continuous path) vs tidal_lines.analyze reference:")
    print(f"   M2  spectro ratio={m2.statistic:8.2f} ({m2.verdict})")
    print(f"   M2  tidal   ratio={m2ref['sharp_line_ratio']:8.2f} ({m2ref['verdict']})")
    assert m2.verdict == m2ref["verdict"]
    assert round(m2.statistic, 2) == m2ref["sharp_line_ratio"], "tidal path drifted from reference!"

    # --- DETERMINISM: same input -> same digest ---
    d1 = analyze_spectrum(spec, GAMMA).digest
    d2 = analyze_spectrum(spec, GAMMA).digest
    assert d1 == d2
    print(f"\nDETERMINISM  recompute digest stable: {d1[:24]}...")

    print("\nALL DOMAINS PASSED - XRF, gamma, array, tides(consistent), deterministic.")


if __name__ == "__main__":
    self_test()
