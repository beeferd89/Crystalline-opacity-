"""
cole_fit.py  —  the vessel-wall RC reader

The one software piece between "conceptually complete" and "produces a read
you can show someone." Takes swept bioimpedance (magnitude+phase, or complex Z,
per node) and pulls the RC parameters out per node, with error bars.

Lineage: same discipline as the squid and compound lenses — prove it on data
where the truth is already known BEFORE it ever runs on a real node. Run this
file directly and it validates itself against known-truth synthetic data.

The physics, stated once:
  Tissue is a resistor (extracellular path, current AROUND cells) in parallel
  with a resistor+capacitor (intracellular path through the membrane). That RC
  pair sets a time constant tau = R*C. The Cole model is the standard form:

      Z(w) = Rinf + (R0 - Rinf) / (1 + (j*w*tau)^alpha)

      R0     = DC resistance   (low freq, all current around cells)
      Rinf   = high-freq limit (current through everything)
      tau    = R*C             = the decay-time axis = the adrenochrome glow-down
      alpha  = depression      (0..1; how far real tissue smears off one clean RC)
      fc     = 1/(2*pi*tau)    = center frequency  --> 48 kHz lands HERE by design

Why a sweep and not one point: at a single 48 kHz read you get one complex
number (magnitude + phase = two reals) against four unknowns. Underdetermined.
A handful of points bracketing 48 kHz overdetermines it — that's what makes
tau recoverable instead of assumed.

Two channels (the adrenaline read): adrenaline moves both the eccrine sweat
glands (fast / shallow — the GSR mechanism) and peripheral vessels (slow /
deep — vasoconstriction). Two relaxations, two tau. fit_two_dispersion pulls
them apart from one swept read, which a single-frequency GSR electrode cannot.
Honest limit: the two tau separate cleanly (which channel), but their
amplitudes trade off (how much) and carry larger error bars. Timing reads
sharper than magnitude. Good enough, because which-channel is the thing that
tells sweat-gland from vascular.

Discipline: this READS the body's own catecholamine comeback at the vessel
wall. It never drives the state. Condition the medium, read the comeback,
never steer the tissue.
"""

import numpy as np
from scipy.optimize import curve_fit


# ── single dispersion ──────────────────────────────────────────────────────

def cole_Z(f, R0, Rinf, tau, alpha):
    """Complex Cole impedance at frequency f (Hz). f may be array."""
    w = 2.0 * np.pi * np.asarray(f, float)
    return Rinf + (R0 - Rinf) / (1.0 + (1j * w * tau) ** alpha)


def _stacked(f, R0, Rinf, log_tau, alpha):
    Z = cole_Z(f, R0, Rinf, 10.0 ** log_tau, alpha)
    return np.concatenate([Z.real, Z.imag])


def fit_node(f, Z_meas):
    """
    Fit one node's swept complex impedance to the Cole model.

    f       : array of frequencies (Hz)
    Z_meas  : complex array, same length (real + j*imag, ohms)

    Returns dict: R0, Rinf, tau, alpha, fc, and *_err (1-sigma) for each.
    tau is fit in log space for stability (it lives near 1e-6).
    """
    f = np.asarray(f, float)
    Z_meas = np.asarray(Z_meas, complex)
    y = np.concatenate([Z_meas.real, Z_meas.imag])

    R0_0 = float(Z_meas.real.max())
    Rinf_0 = float(Z_meas.real.min())
    fc_guess = f[np.argmax(-Z_meas.imag)]                  # peak of -Im marks fc
    log_tau_0 = np.log10(1.0 / (2 * np.pi * fc_guess))

    p0 = [R0_0, Rinf_0, log_tau_0, 0.8]
    bounds = ([1, 1, -9, 0.3], [1e6, 1e6, -3, 1.0])
    popt, pcov = curve_fit(_stacked, f, y, p0=p0, bounds=bounds, maxfev=20000)
    perr = np.sqrt(np.diag(pcov))

    tau = 10.0 ** popt[2]
    tau_err = np.log(10) * tau * perr[2]                   # propagate from log
    fc = 1.0 / (2 * np.pi * tau)
    fc_err = np.log(10) * fc * perr[2]
    return dict(
        R0=popt[0], R0_err=perr[0],
        Rinf=popt[1], Rinf_err=perr[1],
        tau=tau, tau_err=tau_err,
        alpha=popt[3], alpha_err=perr[3],
        fc=fc, fc_err=fc_err,
    )


# ── two dispersions (fast sweat-gland + slow vascular) ─────────────────────

def cole2_Z(f, dRA, tauA, aA, dRB, tauB, aB, Rinf):
    """Sum of two Cole terms over a shared high-frequency floor Rinf."""
    w = 2.0 * np.pi * np.asarray(f, float)
    za = dRA / (1.0 + (1j * w * tauA) ** aA)
    zb = dRB / (1.0 + (1j * w * tauB) ** aB)
    return Rinf + za + zb


def _stacked2(f, dRA, ltA, aA, dRB, ltB, aB, Rinf):
    Z = cole2_Z(f, dRA, 10 ** ltA, aA, dRB, 10 ** ltB, aB, Rinf)
    return np.concatenate([Z.real, Z.imag])


def fit_two_dispersion(f, Z_meas, fc_fast_guess=8e4, fc_slow_guess=1.2e4):
    """
    Separate two relaxations from one swept read.
    Channel A = fast (eccrine sweat gland), Channel B = slow (vascular).
    Returns dict with tau_fast, tau_slow (+ errors), amplitudes, alphas, Rinf.
    """
    f = np.asarray(f, float)
    Z_meas = np.asarray(Z_meas, complex)
    y = np.concatenate([Z_meas.real, Z_meas.imag])

    span = float(Z_meas.real.max() - Z_meas.real.min())
    p0 = [span * 0.4, np.log10(1 / (2 * np.pi * fc_fast_guess)), 0.8,
          span * 0.6, np.log10(1 / (2 * np.pi * fc_slow_guess)), 0.8,
          float(Z_meas.real.min())]
    bounds = ([1, -9, 0.3, 1, -9, 0.3, 1],
              [1e5, -3, 1.0, 1e5, -3, 1.0, 1e6])
    popt, pcov = curve_fit(_stacked2, f, y, p0=p0, bounds=bounds, maxfev=40000)
    perr = np.sqrt(np.diag(pcov))

    tauA, tauB = 10 ** popt[1], 10 ** popt[4]
    tauA_e = np.log(10) * tauA * perr[1]
    tauB_e = np.log(10) * tauB * perr[4]
    # order so "fast" is always the smaller tau, regardless of fit order
    chans = sorted([
        dict(tau=tauA, tau_err=tauA_e, dR=popt[0], dR_err=perr[0], alpha=popt[2], alpha_err=perr[2]),
        dict(tau=tauB, tau_err=tauB_e, dR=popt[3], dR_err=perr[3], alpha=popt[5], alpha_err=perr[5]),
    ], key=lambda d: d["tau"])
    fast, slow = chans
    return dict(
        fast=fast, slow=slow, Rinf=popt[6], Rinf_err=perr[6],
        fc_fast=1 / (2 * np.pi * fast["tau"]),
        fc_slow=1 / (2 * np.pi * slow["tau"]),
        separation=slow["tau"] / fast["tau"],
    )


# ── self-validation: prove on known truth before any hardware ──────────────

def _validate():
    rng = np.random.default_rng(7)
    print("=" * 60)
    print("SINGLE-NODE  —  recover one tau from a noisy swept read")
    print("=" * 60)
    T = dict(R0=820.0, Rinf=410.0, tau=3.3e-6, alpha=0.78)   # fc ~ 48 kHz
    f = np.logspace(3, 6, 25)
    Zc = cole_Z(f, **T)
    nl = 0.01 * np.abs(Zc).mean()
    Zm = Zc + rng.normal(0, nl, f.shape) + 1j * rng.normal(0, nl, f.shape)
    r = fit_node(f, Zm)
    truth_fc = 1 / (2 * np.pi * T["tau"])
    rows = [("R0", T["R0"], r["R0"], r["R0_err"], "ohm"),
            ("Rinf", T["Rinf"], r["Rinf"], r["Rinf_err"], "ohm"),
            ("tau", T["tau"], r["tau"], r["tau_err"], "s"),
            ("alpha", T["alpha"], r["alpha"], r["alpha_err"], ""),
            ("fc", truth_fc, r["fc"], r["fc_err"], "Hz")]
    print(f"  {'param':<7}{'truth':>11}{'recovered':>13}{'  1sigma':>12}  2σ?")
    for n, t, v, e, u in rows:
        ok = "yes" if (v - 2 * e) <= t <= (v + 2 * e) else "NO"
        print(f"  {n:<7}{t:>11.4g}{v:>13.4g}  +/-{e:>9.3g}  {ok} {u}")

    rng = np.random.default_rng(11)
    print("\n" + "=" * 60)
    print("TWO-DISPERSION  —  separate fast (sweat) + slow (vascular)")
    print("=" * 60)
    T2 = dict(dRA=180.0, tauA=1.6e-6, aA=0.82,    # fast  fc ~ 100 kHz
              dRB=300.0, tauB=16e-6, aB=0.74,     # slow  fc ~  10 kHz
              Rinf=400.0)
    f2 = np.logspace(np.log10(3e2), np.log10(3e6), 40)
    Zc2 = cole2_Z(f2, **T2)
    nl2 = 0.008 * np.abs(Zc2).mean()
    Zm2 = Zc2 + rng.normal(0, nl2, f2.shape) + 1j * rng.normal(0, nl2, f2.shape)
    rr = fit_two_dispersion(f2, Zm2)
    pairs = [("tau_fast", T2["tauA"], rr["fast"]["tau"], rr["fast"]["tau_err"], "s"),
             ("tau_slow", T2["tauB"], rr["slow"]["tau"], rr["slow"]["tau_err"], "s"),
             ("dR_fast", T2["dRA"], rr["fast"]["dR"], rr["fast"]["dR_err"], "ohm"),
             ("dR_slow", T2["dRB"], rr["slow"]["dR"], rr["slow"]["dR_err"], "ohm"),
             ("Rinf", T2["Rinf"], rr["Rinf"], rr["Rinf_err"], "ohm")]
    print(f"  {'param':<9}{'truth':>11}{'recovered':>13}{'  1sigma':>12}  2σ?")
    for n, t, v, e, u in pairs:
        ok = "yes" if (v - 2 * e) <= t <= (v + 2 * e) else "NO"
        print(f"  {n:<9}{t:>11.4g}{v:>13.4g}  +/-{e:>9.3g}  {ok} {u}")
    print("-" * 60)
    print(f"  fast fc {rr['fc_fast']/1e3:6.1f} kHz   slow fc {rr['fc_slow']/1e3:6.1f} kHz")
    print(f"  separation recovered {rr['separation']:.1f}x  "
          f"(truth {T2['tauB']/T2['tauA']:.1f}x)")
    print("  two channels resolved from ONE swept read.")
    print("\nNote: tau separates cleanly (which channel); amplitudes carry")
    print("larger error (how much). Timing reads sharper than magnitude.")


if __name__ == "__main__":
    _validate()
