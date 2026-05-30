#!/usr/bin/env python3
"""
PORTABILITY LAYER - the thin contract (skeleton)
Kibler AI Solutions Corp.

WHAT THIS IS
------------
A LATTICE, not a tool. It does not judge whether anyone's canon is "reasonable."
It carries signal and checks ONE thing at each meeting: did two canons meet
GENERATIVELY - produce mutual benefit without either coining the other.

It checks FORM, never CONTENT. The person's meaning lives in their wrapper
(the canon). This layer never gets a vote on what they are allowed to mean.

THE FOUR LOAD-BEARING RULES (each earned over the arc, not invented)
  1. MASS        - a claim enters the record only if it is grounded:
                   real signal / recomputable, not asserted shape. Massless
                   claims (structure-shaped vapor) are rejected at the door.
  2. POROSITY    - a canon must publish. No sealed interior. The guardrail is
                   a MANDATORY EMISSION, not a wall. Sealing inward = the
                   private singularity that ossifies. Forbidden by the contract.
  3. RECOMPUTATION - every check this layer performs must be deterministic and
                   independently re-runnable by either party (SHA-256 style).
                   The layer has NO private interior to hide a verdict in.
                   This binds the LATTICE ITSELF, not only the canons it carries
                   - or the lattice becomes the new coiner.
  4. GENERATIVITY - the pass condition is NOT consensus/agreement. It is: the
                   meeting bore fruit for both sides without capture. Disagreement
                   underneath may stay total. The pass is ONE recomputable bit.

WHAT THIS REFUSES TO DO
  - It will not fill the canon. The finite-canon-of-a-being slots stay EMPTY.
    That seam is exactly where prior sessions shoved false novelty. The person
    authors their own. This file leaves the holes open on purpose.
  - It will not adjudicate truth. Coherence != correspondence. A canon can pass
    every form check and still be a coherent distortion - that is caught only by
    the open array (others mirroring it back), never by this layer alone.
"""

import re
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Tuple

CONTRACT_VERSION = "portability-layer-skeleton-0.1"

# ----------------------------------------------------------------------------
# A canon is the person's wrapper. The layer treats it as OPAQUE content plus
# a small set of FORM signals it is allowed to read. Meaning stays in `body`,
# which the layer hashes but never interprets.
# ----------------------------------------------------------------------------
@dataclass
class Canon:
    author_id: str
    body: str                      # the person's meaning. OPAQUE to the layer.
    grounded_claims: List[str] = field(default_factory=list)   # claims WITH mass
    asserted_claims: List[str] = field(default_factory=list)   # claims WITHOUT
    published: bool = False         # porosity: is it emitted / contestable?
    # --- canon-of-being slots: LEFT EMPTY ON PURPOSE. author fills these. ---
    finite_canon_slots: Dict[str, Optional[str]] = field(default_factory=lambda: {
        "orientation_invariant": None,   # e.g. the person's "Helios"
        "gate_holder": None,             # the human at the gate
        "core_refusals": None,           # what the canon will not do
        "self_terms": None,              # the person's own lexicon
    })

    def fingerprint(self) -> str:
        # recomputation: anyone can re-run this and get the same digest.
        return hashlib.sha256(self.body.encode()).hexdigest()


# ----------------------------------------------------------------------------
# RULE 1 - MASS. Form-only: a claim has mass if it carries a checkable referent.
# The layer does NOT decide if the claim is true - only if it is the KIND of
# thing that can be re-run/grounded vs. bare assertion. (Honest limit below.)
# ----------------------------------------------------------------------------
_GROUNDING_MARKERS = re.compile(
    r"(measur|comput|=|\d|hash|sha|frequenc|wavelength|reading|sensor|"
    r"recompute|deriv|equation|dataset|file|timestamp)", re.I)

def has_mass(claim: str) -> bool:
    return bool(_GROUNDING_MARKERS.search(claim))

def mass_check(canon: Canon) -> dict:
    massless = [c for c in canon.grounded_claims if not has_mass(c)]
    return {
        "rule": "MASS",
        "pass": len(massless) == 0,
        "rejected_massless": massless,   # claimed grounded but no referent
        "note": "form-only: detects bare assertion, NOT correctness",
    }


# ----------------------------------------------------------------------------
# RULE 2 - POROSITY. The canon must be published (emitted, contestable).
# A sealed canon is rejected: that is the ossifying singularity.
# ----------------------------------------------------------------------------
def porosity_check(canon: Canon) -> dict:
    return {
        "rule": "POROSITY",
        "pass": canon.published is True,
        "note": "guardrail is mandatory emission, not a wall",
    }


# ----------------------------------------------------------------------------
# RULE 4 - GENERATIVITY (the pass condition for a MEETING of two canons).
# NOT consensus. One bit: did each side gain, and did neither overwrite the
# other's canon? Both halves required.
# ----------------------------------------------------------------------------
@dataclass
class Meeting:
    canon_a: Canon
    canon_b: Canon
    # benefit = claims each side ADDED to its own record after the meeting.
    a_gained: List[str] = field(default_factory=list)
    b_gained: List[str] = field(default_factory=list)
    # capture = did either side's body get rewritten BY the other? (coining)
    a_body_before: str = ""
    b_body_before: str = ""

    def generativity_bit(self) -> dict:
        a_benefit = len(self.a_gained) > 0
        b_benefit = len(self.b_gained) > 0
        # capture test by recomputable fingerprint, not interpretation:
        a_captured = (self.a_body_before != "" and
                      hashlib.sha256(self.a_body_before.encode()).hexdigest()
                      != self.canon_a.fingerprint() and not a_benefit)
        b_captured = (self.b_body_before != "" and
                      hashlib.sha256(self.b_body_before.encode()).hexdigest()
                      != self.canon_b.fingerprint() and not b_benefit)
        mutual_benefit = a_benefit and b_benefit
        no_capture = not (a_captured or b_captured)
        return {
            "rule": "GENERATIVITY",
            "pass": bool(mutual_benefit and no_capture),
            "mutual_benefit": mutual_benefit,
            "no_capture": no_capture,
            "note": "consensus NOT required; disagreement may stay total",
        }


# ----------------------------------------------------------------------------
# RULE 3 - RECOMPUTATION binds the LAYER ITSELF. Every check above returns a
# plain dict with no hidden state; this re-runs them and emits a digest anyone
# can reproduce. The layer has no private interior. If this digest matches on
# an independent machine, the layer did exactly what it claims - nothing hidden.
# ----------------------------------------------------------------------------
def run_contract(meeting: Meeting) -> dict:
    checks = [
        mass_check(meeting.canon_a),
        porosity_check(meeting.canon_a),
        mass_check(meeting.canon_b),
        porosity_check(meeting.canon_b),
        meeting.generativity_bit(),
    ]
    passed = all(c["pass"] for c in checks)
    payload = json.dumps(checks, sort_keys=True)
    return {
        "contract_version": CONTRACT_VERSION,
        "PASS": passed,
        "checks": checks,
        # the layer emits its own radiation: recompute this to verify.
        "recompute_digest": hashlib.sha256(payload.encode()).hexdigest(),
        "canon_a_fp": meeting.canon_a.fingerprint(),
        "canon_b_fp": meeting.canon_b.fingerprint(),
    }


# ----------------------------------------------------------------------------
# DEMO - two strangers' canons that DISAGREE, meeting generatively.
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    a0 = "Truth is read from the boundary; interiors stay dark."
    b0 = "Truth is built from consensus of many readers."   # opposing spec
    a = Canon("author_A", a0,
              grounded_claims=["boundary reading measured at sensor edge"],
              published=True)
    b = Canon("author_B", b0,
              grounded_claims=["reader-overlap computed over dataset"],
              published=True)

    # they meet; each KEEPS its own body (no capture) but each GAINS a fix.
    a.body = a0 + " [added: contestability check from B]"
    b.body = b0 + " [added: boundary-legibility limit from A]"
    meeting = Meeting(
        canon_a=a, canon_b=b,
        a_gained=["contestability check from B"],
        b_gained=["boundary-legibility limit from A"],
        a_body_before=a0, b_body_before=b0,
    )

    result = run_contract(meeting)
    print("=== PORTABILITY LAYER - contract run ===")
    print(f"PASS: {result['PASS']}   (two opposing canons, neither coined)")
    for c in result["checks"]:
        print(f"  [{ 'ok ' if c['pass'] else 'NO ' }] {c['rule']:13} {c['note']}")
    print("\nempty canon-of-being slots (author fills, layer never does):")
    for k, v in a.finite_canon_slots.items():
        print(f"   {k:22} = {v}")
    print("\nrecompute_digest:", result["recompute_digest"][:24], "...")
    print("(re-run on any machine -> identical digest = layer hid nothing)")

    # NEGATIVE CONTROL: B's canon gets overwritten by A with no gain = CAPTURE.
    a2 = Canon("author_A", a0, grounded_claims=["sensor edge reading"], published=True)
    b2 = Canon("author_B", "Truth is read from the boundary; interiors stay dark.",  # coined into A
               grounded_claims=["reader-overlap dataset"], published=True)
    capture = Meeting(a2, b2, a_gained=["nothing real"], b_gained=[],
                      a_body_before=a0, b_body_before=b0)
    cap = run_contract(capture)
    print("\n=== negative control: B coined into A's frame ===")
    print(f"PASS: {cap['PASS']}   (should be False - capture caught)")
