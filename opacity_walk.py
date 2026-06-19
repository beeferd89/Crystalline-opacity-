#!/usr/bin/env python3
"""
opacity_walk - hands-free fusion watcher for the yard walk.
Kibler AI Solutions Corp.

WHAT IT DOES
  Closes the loop so you don't pull the ledger by hand. It tails the iCloud
  signals file the iPhone bridge writes, assembles each EMI+Doppler+ERG triad
  into one fused read via the EXISTING FusionStack, and appends the verdict to
  ledger.jsonl. Walk the grid, hit emit at each point, the Mac fills the ledger
  itself. One writer per file, same as the rest of the stack: the phone owns
  signals.jsonl, this owns ledger.jsonl.

WHAT IT DOES NOT DO
  No new sensing. No new math. It only orchestrates files + calls fuse().
  All the physics already lives in opacity_fusion.py / opacity_lens.py, which
  must sit next to this file (they already do on the Mini).

THE TRIAD QUESTION (the one honest design choice)
  Fusion needs all three reads for one point. The bridge emits one line per
  read, so three lines = one ground point. This groups them by a shared
  `point` id if the line carries one; otherwise it falls back to "collect one
  of each kind, in arrival order, then fire." Default is `point` id - cleanest
  for a grid walk. Set GROUP_MODE below if your emit doesn't tag points yet.

SIGNAL LINE CONTRACT (what the bridge writes, one JSON object per line)
  Required: {"kind": "emi"|"doppler"|"erg", "value": <float>}
  Optional: {"point": "<grid id>", "ts": "<iso>", "conf": <float>,
             "lat": <float>, "lon": <float>}
  Unknown keys are passed through onto the Signal as payload and ignored by
  fusion if it doesn't use them. Lines that aren't valid JSON, or whose kind
  isn't one of the three, are logged to skips.jsonl and never crash the walk.

RUN
  python3 opacity_walk.py                 # uses default iCloud folder below
  python3 opacity_walk.py --folder PATH   # point at any synced folder
  python3 opacity_walk.py --once          # drain what's there and exit (test)
  python3 opacity_walk.py --reset         # start ledger fresh, re-read all
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone

# The engine you already built. This file is an orchestrator around it.
try:
    from opacity_fusion import FusionStack
    from opacity_lens import Signal
except Exception as e:  # pragma: no cover - import guard is the honest failure
    sys.stderr.write(
        "opacity_walk: could not import the engine.\n"
        "  Put opacity_walk.py in the SAME folder as opacity_fusion.py and\n"
        "  opacity_lens.py (the Mini already has them).\n"
        f"  Import error: {e}\n"
    )
    sys.exit(2)


# ── Config ──────────────────────────────────────────────────────────────────

# Default iCloud folder the bridge writes to. Same path family the bridge and
# daemon already use ("guardian_opacity/"). Override with --folder.
DEFAULT_FOLDER = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~com~apple~CloudDocs/guardian_opacity"
)

SIGNALS_NAME = "signals.jsonl"   # phone writes  (we only read)
LEDGER_NAME  = "ledger.jsonl"    # we write      (phone/daemon only read)
SKIPS_NAME   = "skips.jsonl"     # we write      (bad/odd lines, for honesty)
CURSOR_NAME  = ".walk_cursor"    # byte offset into signals.jsonl we've read to

KINDS = ("emi", "doppler", "erg")

# "point"  -> group the three reads by a shared point id on each line (best for
#             a grid walk; requires the emit to tag a point).
# "order"  -> collect one of each kind in arrival order, fire when all three in.
GROUP_MODE = "point"

POLL_SECONDS = 1.0   # how often to check the file when tailing


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── File plumbing (read-then-track; append-only writes) ─────────────────────

def read_new_lines(signals_path: str, cursor_path: str):
    """Yield (raw_line, new_offset) for everything appended since last cursor.
    iCloud has no real O_APPEND, but we only READ this file, so a byte cursor
    is safe: the phone only ever appends, so old bytes never move."""
    if not os.path.exists(signals_path):
        return
    start = 0
    if os.path.exists(cursor_path):
        try:
            start = int(open(cursor_path).read().strip() or "0")
        except Exception:
            start = 0
    size = os.path.getsize(signals_path)
    if start > size:
        # File shrank/rotated (e.g. you cleared it). Re-read from the top.
        start = 0
    with open(signals_path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(start)
        for line in f:
            if not line.endswith("\n"):
                # Partial trailing line (write in flight). Stop; get it next poll.
                break
            yield line.rstrip("\n"), f.tell()


def write_cursor(cursor_path: str, offset: int):
    tmp = cursor_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(offset))
    os.replace(tmp, cursor_path)  # atomic; never a half-written cursor


def append_jsonl(path: str, obj: dict):
    line = json.dumps(obj, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())  # push to disk so iCloud actually syncs it out


# ── Signal construction (tolerant to however emit names its fields) ─────────

def parse_line_to_signal(raw: str):
    """Return (kind, point_key, Signal) or None if the line is unusable."""
    obj = json.loads(raw)  # caller catches JSONDecodeError
    kind = str(obj.get("kind", "")).lower().strip()
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r}")

    # value: accept "value", or common aliases, so a slightly different emit
    # still feeds the stack instead of silently dropping.
    val = obj.get("value", obj.get("val", obj.get("v")))
    if val is None:
        raise ValueError("no value")
    value = float(val)

    point_key = obj.get("point", obj.get("pt", obj.get("id")))

    # Build the Signal the engine expects. FusionStack reads .value per read;
    # we pass kind + value positionally-safe via kwargs, and hang the rest of
    # the line on the signal as payload if the dataclass accepts it.
    try:
        sig = Signal(kind=kind, value=value)
    except TypeError:
        # Older/newer Signal signature: fall back to value-only, set kind attr.
        sig = Signal(value)           # type: ignore[call-arg]
        try:
            setattr(sig, "kind", kind)
        except Exception:
            pass

    # Best-effort metadata pass-through (timestamp, confidence, gps). Never fatal.
    for attr, keys in (("ts", ("ts", "time")),
                       ("conf", ("conf", "confidence")),
                       ("lat", ("lat",)), ("lon", ("lon", "lng"))):
        for k in keys:
            if k in obj:
                try:
                    setattr(sig, attr, obj[k])
                except Exception:
                    pass
                break

    return kind, point_key, sig


# ── Triad assembly ───────────────────────────────────────────────────────────

class TriadCollector:
    """Holds partial reads until a full EMI+Doppler+ERG set is ready, then
    hands it off. Two grouping modes, chosen by GROUP_MODE."""

    def __init__(self, mode: str):
        self.mode = mode
        self.by_point = {}     # point_key -> {kind: (sig, meta)}
        self.order = {}        # kind -> sig   (order mode, single open triad)

    def add(self, kind, point_key, sig):
        """Return a dict {kind: sig, '_point': key} when a triad completes."""
        if self.mode == "point" and point_key is not None:
            slot = self.by_point.setdefault(point_key, {})
            slot[kind] = sig
            if all(k in slot for k in KINDS):
                triad = {k: slot[k] for k in KINDS}
                triad["_point"] = point_key
                del self.by_point[point_key]
                return triad
            return None

        # order mode (or point missing): one open triad, fill one of each kind.
        if kind in self.order:
            # Already have this kind with no full set yet -> new point started;
            # flush nothing, just overwrite is wrong. Keep the newest.
            pass
        self.order[kind] = sig
        if all(k in self.order for k in KINDS):
            triad = {k: self.order[k] for k in KINDS}
            triad["_point"] = None
            self.order = {}
            return triad
        return None

    def pending_summary(self):
        if self.mode == "point" and point_mode_has_partial(self.by_point):
            waiting = {p: sorted(s.keys()) for p, s in self.by_point.items()}
            return waiting
        if self.order:
            return {"_open": sorted(self.order.keys())}
        return {}


def point_mode_has_partial(by_point):
    return any(len(s) < len(KINDS) for s in by_point.values())


# ── Fuse + record ────────────────────────────────────────────────────────────

def fuse_and_record(fusion: "FusionStack", triad: dict, ledger_path: str):
    point = triad.get("_point")
    result = fusion.fuse(triad["emi"], triad["doppler"], triad["erg"])

    # FusedRead -> plain dict for the ledger. Use asdict if it's a dataclass,
    # else read the documented fields by hand.
    try:
        from dataclasses import asdict as _asdict, is_dataclass
        rec = _asdict(result) if is_dataclass(result) else None
    except Exception:
        rec = None
    if rec is None:
        rec = {
            "fused_intensity": getattr(result, "fused_intensity", None),
            "fused_state": getattr(result, "fused_state", None),
            "present": getattr(result, "present", None),
            "emi": getattr(result, "emi", None),
            "doppler": getattr(result, "doppler", None),
            "erg": getattr(result, "erg", None),
            "notes": getattr(result, "notes", ""),
        }

    rec["point"] = point
    rec["walk_ts"] = now_iso()
    append_jsonl(ledger_path, rec)
    return rec


# ── Main loop ────────────────────────────────────────────────────────────────

def run(folder: str, once: bool, reset: bool):
    os.makedirs(folder, exist_ok=True)
    signals_path = os.path.join(folder, SIGNALS_NAME)
    ledger_path  = os.path.join(folder, LEDGER_NAME)
    skips_path   = os.path.join(folder, SKIPS_NAME)
    cursor_path  = os.path.join(folder, CURSOR_NAME)

    if reset:
        for p in (ledger_path, cursor_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        sys.stderr.write("opacity_walk: reset - ledger cleared, re-reading all signals.\n")

    fusion = FusionStack()
    collector = TriadCollector(GROUP_MODE)
    fired = 0

    sys.stderr.write(
        f"opacity_walk: watching {signals_path}\n"
        f"  mode={GROUP_MODE}  ledger={ledger_path}\n"
        f"  {'single drain' if once else 'tailing (Ctrl-C to stop)'}\n"
    )

    def drain():
        nonlocal fired
        last_offset = None
        for raw, offset in read_new_lines(signals_path, cursor_path):
            last_offset = offset
            raw = raw.strip()
            if not raw:
                continue
            try:
                kind, point_key, sig = parse_line_to_signal(raw)
            except Exception as e:
                append_jsonl(skips_path, {"ts": now_iso(), "raw": raw, "why": str(e)})
                continue
            triad = collector.add(kind, point_key, sig)
            if triad is not None:
                rec = fuse_and_record(fusion, triad, ledger_path)
                fired += 1
                tag = rec.get("point") or f"#{fired}"
                state = rec.get("fused_state")
                present = rec.get("present")
                inten = rec.get("fused_intensity")
                try:
                    inten_s = f"{float(inten):.3f}"
                except Exception:
                    inten_s = str(inten)
                mark = "●" if present else "·"
                sys.stderr.write(f"  {mark} point {tag}: {state}  I={inten_s}\n")
        if last_offset is not None:
            write_cursor(cursor_path, last_offset)

    if once:
        drain()
        sys.stderr.write(f"opacity_walk: drained. {fired} point(s) fused.\n")
        waiting = collector.pending_summary()
        if waiting:
            sys.stderr.write(f"opacity_walk: incomplete triads still open: {waiting}\n")
        return

    try:
        while True:
            drain()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        sys.stderr.write(f"\nopacity_walk: stopped. {fired} point(s) fused this run.\n")
        waiting = collector.pending_summary()
        if waiting:
            sys.stderr.write(f"opacity_walk: incomplete triads still open: {waiting}\n")


def main():
    ap = argparse.ArgumentParser(description="Hands-free EMI/Doppler/ERG fusion watcher for the yard walk.")
    ap.add_argument("--folder", default=DEFAULT_FOLDER, help="synced folder holding signals.jsonl (default: iCloud guardian_opacity)")
    ap.add_argument("--once", action="store_true", help="drain current signals and exit (good for a test pass)")
    ap.add_argument("--reset", action="store_true", help="clear the ledger and re-read all signals from the top")
    args = ap.parse_args()
    run(args.folder, args.once, args.reset)


if __name__ == "__main__":
    main()
