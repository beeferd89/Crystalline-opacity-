"""
kinect_optical.py  --  Kibler AI Solutions Corp.
The OPTICAL facet of the spectrometer + X-ray finite array.

WHAT THIS IS
  An IngestSource for spectro_core: it reads near-IR / visible intensity off a
  Kinect-360 IR camera, collapses the dispersed (grating-fanned) axis of the
  frame into intensity-per-wavelength, and emits a Spectrum through the SAME
  contract the keV (gamma / XRF) sources use. The kernel does not change. This
  is a THIRD line table (nm) and a driver -- nothing more.

  Same kernel, three line tables:
      gamma   -> isotope lines, axis in keV   (shipped, verified)
      XRF     -> element lines,  axis in keV   (shipped, verified)
      optical -> emission lines, axis in nm    (THIS FILE)

WHY THE SHAPE IS THE WAY IT IS
  - core imports zero hardware libs. So numpy and libfreenect are imported ONLY
    inside this driver (transport), and the Spectrum that crosses the contract
    carries PLAIN PYTHON LISTS. spectro_core can ingest it without importing
    numpy or any device lib. Governance stays separated from transport.
  - every read carries a sha256 determinism digest. Two identical frames in ->
    byte-identical digest out. The read is its own receipt.
  - BOTH shapes: Spectrum is the rich faceted object (roi, calibration, source
    meta, digest, timestamp) AND exposes .as_pair() -> (channels, intensities),
    the bare two-array form the parent analyze(times, values) forces. The kernel
    can consume either.
  - MULTIFACETED: a KinectOpticalSource is ONE facet. optical_facet() wraps it
    as an array-ready facet that joins the existing gamma + XRF facets at the
    array's 2/3 consensus vote. The optical facet does not out-vote the others;
    it stands beside them.

THE ONE FALSIFIABLE QUESTION (audit before you trust it)
  Given a frame with a grating-dispersed spectrum, does a real emission line
  stand up as a SHARP peak above the local background, while broadband glow and
  hot pixels do NOT? The synthetic self-test answers this with no Kinect
  attached: known lines -> detected, non-line bump -> rejected, digest stable.

NO network here. The Kinect (or a saved frame) is the source; this does the
collapse, the calibration, and the receipt. Detection itself lives in
spectro_core -- this file's self-test carries only a minimal audit harness to
prove the ingested spectrum is well-formed.

Usage:
  python3 kinect_optical.py            # synthetic self-test (audit the path)
  python3 kinect_optical.py live       # read one frame from a live Kinect
  python3 kinect_optical.py frame.npy  # read a saved IR frame (numpy .npy)
"""

from __future__ import annotations

import sys
import json
import math
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Sequence, Callable, Dict, List, Tuple

# numpy is TRANSPORT-side only. Guarded so the module still imports for the
# synthetic path on a box without it. core never imports this file.
try:
    import numpy as _np
except Exception:  # pragma: no cover - environment without numpy
    _np = None


# ---------------------------------------------------------------------------
# OPTICAL LINE TABLE  --  the nm sibling of the keV isotope/element tables.
# Values are vacuum/air emission wavelengths in nanometers. Extend freely; the
# kernel reads whatever table it is handed. Two of these double as CALIBRATION
# anchors (see DEFAULT_ANCHORS): the Kinect's own 830 nm structured-light
# projector, and a cheap 532 nm green laser pointer.
# ---------------------------------------------------------------------------
OPTICAL_LINES: Dict[str, float] = {
    # calibration-grade, sharp, easy to source
    "Kinect_IR_proj": 830.0,   # Kinect 360 structured-light projector line
    "GreenLaser_532": 532.0,   # frequency-doubled Nd:YAG pointer
    "HeNe_633":       632.8,   # helium-neon, if on hand
    # common atomic emission (flame / discharge / mineral fluorescence)
    "Na_D":           589.3,   # sodium doublet (table salt in flame)
    "H_alpha":        656.3,   # hydrogen Balmer-alpha
    "H_beta":         486.1,   # hydrogen Balmer-beta
    "K_violet":       404.7,   # potassium
    "Hg_546":         546.1,   # mercury green (fluorescent tube)
    "Hg_436":         435.8,   # mercury blue
    # mineral / rockhound fluorescence markers (UV-pumped emission)
    "Mn_red":         640.0,   # Mn2+ in calcite -> red
    "UV_uranyl":      525.0,   # uranyl glass -> green
}

# the lines that matter most for "is this calibration trustworthy": the two
# anchors. Mirrors PRIMARY=("M2","S2") in tidal_lines.
PRIMARY_OPTICAL = ("Kinect_IR_proj", "GreenLaser_532")

# default two-point calibration anchors: (column_index_seen, true_nm).
# You MEASURE the two column indices once on your rig, drop them in here.
DEFAULT_ANCHORS: Tuple[Tuple[float, float], Tuple[float, float]] = (
    (96.0, 532.0),    # green laser landed near column 96   <-- MEASURE on rig
    (560.0, 830.0),   # Kinect IR projector near column 560 <-- MEASURE on rig
)


# ---------------------------------------------------------------------------
# CALIBRATION  --  column index -> nm, two-point linear fit.
# Direct sibling of the keV calibration: map raw channel -> physical unit using
# two known lines. There the unit was keV (Am-241 59.5, Cs-137 661.7); here it
# is nm (532 green, 830 Kinect IR). Same two-point structure, different axis.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LinearCalibration:
    slope: float       # nm per column
    intercept: float   # nm at column 0
    anchors: Tuple[Tuple[float, float], Tuple[float, float]]
    unit: str = "nm"

    @classmethod
    def from_two_lines(
        cls,
        anchors: Tuple[Tuple[float, float], Tuple[float, float]] = DEFAULT_ANCHORS,
    ) -> "LinearCalibration":
        (c0, w0), (c1, w1) = anchors
        if c1 == c0:
            raise ValueError("calibration anchors share a column index")
        slope = (w1 - w0) / (c1 - c0)
        intercept = w0 - slope * c0
        return cls(slope=slope, intercept=intercept, anchors=anchors)

    def column_to_nm(self, columns: Sequence[float]) -> List[float]:
        return [self.slope * c + self.intercept for c in columns]


# ---------------------------------------------------------------------------
# SPECTRUM  --  the object that crosses the IngestSource contract.
# Plain-list payload so core needs no numpy. Rich faceted metadata alongside.
# .as_pair() returns the bare (channels, intensities) two-array form.
# .digest is the sha256 determinism receipt over the canonical payload.
# ---------------------------------------------------------------------------
@dataclass
class Spectrum:
    channels: List[float]                 # wavelengths in nm (post-calibration)
    intensities: List[float]              # collapsed intensity per channel
    unit: str = "nm"
    source: str = "kinect_optical"
    modality: str = "optical"             # facet label for the array
    calibration: Optional[dict] = None    # serialized LinearCalibration
    roi: Optional[dict] = None            # which rows/cols were collapsed
    captured_unix: float = 0.0
    meta: dict = field(default_factory=dict)
    digest: str = ""                      # filled by stamp()

    # --- BOTH shapes: the bare two-array form the kernel's parent expects ----
    def as_pair(self) -> Tuple[List[float], List[float]]:
        """(channels, intensities) -- mirrors analyze(times, values)."""
        return self.channels, self.intensities

    def canonical_payload(self) -> dict:
        """Exactly the bytes the digest is taken over. Excludes the digest
        itself and excludes wall-clock so identical frames hash identically.
        Intensities are rounded to a fixed grid so float noise in the last
        ULP does not break determinism."""
        return {
            "channels": [round(c, 6) for c in self.channels],
            "intensities": [round(v, 6) for v in self.intensities],
            "unit": self.unit,
            "source": self.source,
            "modality": self.modality,
            "calibration": self.calibration,
            "roi": self.roi,
        }

    def stamp(self) -> "Spectrum":
        blob = json.dumps(self.canonical_payload(), sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        self.digest = hashlib.sha256(blob).hexdigest()
        return self

    def to_report(self) -> dict:
        """Full faceted report, digest included. This is what you'd persist to
        the Guardian vault: receipt-bearing, inspectable."""
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# THE CONTRACT  --  IngestSource. spectro_core depends on THIS, not on Kinect.
# Defined here as the generalization of analyze() forces it; if spectro_core
# already declares an IngestSource, delete this and import that one -- the
# method name read_spectrum() is the single binding seam.
# ---------------------------------------------------------------------------
class IngestSource:
    """Transport-agnostic source. One method. Returns a stamped Spectrum."""
    def read_spectrum(self) -> Spectrum:  # pragma: no cover - interface
        raise NotImplementedError

    # optional: sources that can stream expose this; the array may poll it.
    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# THE DRIVER  --  KinectOpticalSource.
# Reads an IR frame (live via libfreenect, or a saved .npy, or synthetic),
# collapses the dispersed axis to per-column intensity, calibrates to nm,
# emits a stamped Spectrum. libfreenect is imported lazily, INSIDE the open
# path, so importing this module never requires the device lib.
# ---------------------------------------------------------------------------
@dataclass
class ROI:
    row_lo: int = 200      # collapse only these rows (the slit's image band)
    row_hi: int = 280
    col_lo: int = 0
    col_hi: int = 640

    def as_dict(self) -> dict:
        return asdict(self)


class KinectOpticalSource(IngestSource):
    def __init__(
        self,
        calibration: Optional[LinearCalibration] = None,
        roi: Optional[ROI] = None,
        device_index: int = 0,
        # inject a frame for testing / saved-file replay; if None, go live.
        frame_provider: Optional[Callable[[], "object"]] = None,
    ):
        self.calibration = calibration or LinearCalibration.from_two_lines()
        self.roi = roi or ROI()
        self.device_index = device_index
        self._frame_provider = frame_provider
        self._freenect = None  # lazy

    # -- frame acquisition ---------------------------------------------------
    def _grab_ir_frame(self):
        """Return a 2D intensity array (rows x cols). numpy if available."""
        if self._frame_provider is not None:
            return self._frame_provider()
        # LIVE path: import the device lib here and only here.
        if self._freenect is None:
            import freenect  # transport-only dependency  # noqa
            self._freenect = freenect
        # set the camera to IR mode and pull one frame.
        # video_ir returns a (480, 640) array of IR intensity.
        frame, _ts = self._freenect.sync_get_video(
            self.device_index, self._freenect.VIDEO_IR_8BIT
        )
        return frame

    # -- collapse the dispersed axis ----------------------------------------
    def _collapse(self, frame) -> List[float]:
        """Within the ROI rows, take the MEDIAN intensity down each column.
        Median (not mean) so a single hot pixel in a column cannot fake a line
        -- the spectral analog of tidal_lines using a robust local background.
        Returns one intensity per column across [col_lo, col_hi)."""
        r0, r1 = self.roi.row_lo, self.roi.row_hi
        c0, c1 = self.roi.col_lo, self.roi.col_hi

        if _np is not None and hasattr(frame, "shape"):
            band = _np.asarray(frame)[r0:r1, c0:c1].astype("float64")
            col_med = _np.median(band, axis=0)
            return [float(x) for x in col_med]

        # pure-python fallback (frame is list-of-rows)
        out: List[float] = []
        for c in range(c0, c1):
            col = sorted(float(frame[r][c]) for r in range(r0, r1))
            n = len(col)
            med = col[n // 2] if n % 2 else 0.5 * (col[n // 2 - 1] + col[n // 2])
            out.append(med)
        return out

    # -- the contract method -------------------------------------------------
    def read_spectrum(self) -> Spectrum:
        frame = self._grab_ir_frame()
        intensities = self._collapse(frame)
        columns = list(range(self.roi.col_lo, self.roi.col_lo + len(intensities)))
        wavelengths = self.calibration.column_to_nm(columns)

        spec = Spectrum(
            channels=wavelengths,
            intensities=intensities,
            unit=self.calibration.unit,
            source="kinect_optical",
            modality="optical",
            calibration={
                "slope": self.calibration.slope,
                "intercept": self.calibration.intercept,
                "anchors": self.calibration.anchors,
                "unit": self.calibration.unit,
            },
            roi=self.roi.as_dict(),
            captured_unix=time.time(),
            meta={"device_index": self.device_index, "n_channels": len(columns)},
        )
        return spec.stamp()

    def close(self) -> None:
        if self._freenect is not None:
            try:
                self._freenect.sync_stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ARRAY FACET  --  make the optical source array-ready.
# The array runs 2/3 consensus across modalities. This wraps the optical source
# so it presents the SAME facet shape the gamma and XRF facets present, and
# joins their vote without out-weighting them.
# ---------------------------------------------------------------------------
@dataclass
class Facet:
    modality: str
    source: IngestSource

    def sample(self) -> Spectrum:
        return self.source.read_spectrum()


def optical_facet(
    calibration: Optional[LinearCalibration] = None,
    roi: Optional[ROI] = None,
    frame_provider: Optional[Callable[[], "object"]] = None,
) -> Facet:
    """Return the optical facet for registration into spectro_core's array,
    e.g.  array.register([gamma_facet, xrf_facet, optical_facet()])."""
    return Facet(
        modality="optical",
        source=KinectOpticalSource(
            calibration=calibration, roi=roi, frame_provider=frame_provider
        ),
    )


# ===========================================================================
# AUDIT HARNESS  (self-test)  --  prove the path before any Kinect is attached.
# This MIRRORS tidal_lines.py's synthetic self-test: build a signal with KNOWN
# lines + noise, run it through the real read_spectrum(), and confirm the lines
# are recoverable as sharp peaks while a broad non-line bump is rejected. The
# detection logic here is a MINIMAL local-contrast check only -- spectro_core
# owns real detection. We are auditing the INGEST, not replacing the kernel.
# ===========================================================================

def _synthetic_ir_frame(
    cols: int = 640,
    rows: int = 480,
    lines_nm: Sequence[float] = (532.0, 830.0, 589.3),
    broad_bump_nm: float = 700.0,
    calibration: Optional[LinearCalibration] = None,
    seed: int = 11,
):
    """Forge a Kinect-like IR frame: a dim background, a few SHARP emission
    lines at known nm (mapped back to columns through the calibration), one
    BROAD low bump that must NOT be called a line, plus a couple of hot pixels
    that the median-collapse must ignore."""
    cal = calibration or LinearCalibration.from_two_lines()
    rng = _np.random.default_rng(seed)

    # background glow + read noise
    frame = rng.normal(8.0, 1.5, size=(rows, cols))

    def nm_to_col(nm: float) -> float:
        # invert the linear calibration
        return (nm - cal.intercept) / cal.slope

    r0, r1 = 200, 280  # the slit-image band the ROI will collapse
    xs = _np.arange(cols)

    # sharp lines: narrow Gaussians in column space, full height across the band
    for nm in lines_nm:
        c = nm_to_col(nm)
        if 0 <= c < cols:
            profile = 120.0 * _np.exp(-0.5 * ((xs - c) / 1.6) ** 2)
            frame[r0:r1, :] += profile[None, :]

    # broad bump: wide + low -> high integrated power but NOT sharp
    cb = nm_to_col(broad_bump_nm)
    if 0 <= cb < cols:
        bump = 14.0 * _np.exp(-0.5 * ((xs - cb) / 40.0) ** 2)
        frame[r0:r1, :] += bump[None, :]

    # hot pixels: single bright dots -> median down the column must kill these
    for _ in range(6):
        rr = int(rng.integers(r0, r1))
        cc = int(rng.integers(0, cols))
        frame[rr, cc] += 250.0

    return _np.clip(frame, 0, 255)


def _sharp_peaks(channels: List[float], intensities: List[float],
                 win: int = 25, k: float = 6.0) -> List[Tuple[float, float]]:
    """Minimal audit detector: a channel is a 'line' if its intensity exceeds
    the LOCAL median by k robust-sigma. Robust sigma via MAD. This is the
    spectral analog of tidal_lines' sharp_line_ratio (peak / local background).
    Returns [(nm, z)]."""
    n = len(intensities)
    out: List[Tuple[float, float]] = []
    for i in range(n):
        lo = max(0, i - win)
        hi = min(n, i + win + 1)
        local = sorted(intensities[lo:hi])
        m = local[len(local) // 2]
        mad = sorted(abs(v - m) for v in local)[len(local) // 2]
        sigma = 1.4826 * mad if mad > 1e-9 else 1e-9
        z = (intensities[i] - m) / sigma
        if z >= k:
            # keep only local maxima so a fat peak reports once
            if intensities[i] >= intensities[max(0, i - 1)] and \
               intensities[i] >= intensities[min(n - 1, i + 1)]:
                out.append((channels[i], z))
    return out


def _self_test() -> int:
    if _np is None:
        print("FAIL: numpy required for the synthetic self-test")
        return 1

    cal = LinearCalibration.from_two_lines()
    known = [532.0, 830.0, 589.3]
    bump = 700.0

    frame = _synthetic_ir_frame(lines_nm=known, broad_bump_nm=bump, calibration=cal)
    src = KinectOpticalSource(calibration=cal,
                              frame_provider=lambda: frame)

    spec = src.read_spectrum()

    # 1) BOTH shapes are coherent
    ch, inten = spec.as_pair()
    assert len(ch) == len(inten) == spec.meta["n_channels"], "pair/length mismatch"

    # 2) the lines stand up; the broad bump does not
    peaks = _sharp_peaks(ch, inten)
    found_nm = [p[0] for p in peaks]

    def near(target, got, tol=4.0):
        return any(abs(g - target) <= tol for g in got)

    ok_lines = all(near(t, found_nm) for t in known)
    bump_rejected = not near(bump, found_nm, tol=8.0)

    # 3) determinism: identical frame -> identical digest
    spec2 = KinectOpticalSource(calibration=cal,
                                frame_provider=lambda: frame).read_spectrum()
    digest_stable = (spec.digest == spec2.digest)

    # 4) hot pixels did not forge lines (median collapse worked): no peak should
    #    sit on a wildly off-grid column with no known line near it
    spurious = [nm for nm in found_nm
                if not any(abs(nm - t) <= 4.0 for t in known)]

    print("optical ingest self-test")
    print("  channels:           ", len(ch))
    print("  calibration nm/col:  %.4f   intercept: %.2f nm"
          % (cal.slope, cal.intercept))
    print("  peaks found (nm):   ", [round(x, 1) for x in found_nm])
    print("  known lines:        ", known)
    print("  broad bump @ %.0f:    %s" % (bump, "REJECTED" if bump_rejected else "leaked"))
    print("  spurious peaks:     ", [round(x, 1) for x in spurious] or "none")
    print("  digest:             ", spec.digest[:16], "...")
    print("  digest stable:      ", digest_stable)

    passed = ok_lines and bump_rejected and digest_stable and not spurious
    print("  VERDICT:            ", "PASS" if passed else "FAIL")
    return 0 if passed else 1


def _read_npy(path: str) -> int:
    if _np is None:
        print("numpy required to read a .npy frame"); return 1
    frame = _np.load(path)
    src = KinectOpticalSource(frame_provider=lambda: frame)
    spec = src.read_spectrum()
    print(json.dumps(spec.to_report(), indent=2)[:2000])
    return 0


def _read_live() -> int:
    src = KinectOpticalSource()
    try:
        spec = src.read_spectrum()
    finally:
        src.close()
    print(json.dumps(spec.to_report(), indent=2)[:2000])
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "live":
        sys.exit(_read_live())
    elif arg.endswith(".npy"):
        sys.exit(_read_npy(arg))
    else:
        sys.exit(_self_test())
