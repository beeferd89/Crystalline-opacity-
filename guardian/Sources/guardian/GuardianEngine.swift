import Foundation

// ============================================================
// GuardianEngine — PUBLIC HARNESS
//
// This is the GitHub-safe harness. It runs the daemon loop, holds
// state, advances the cycle counter, and exposes status. It does
// NOT contain the CrystallineOpacity algorithm.
//
// The four novel patent elements (φ-spiral basis weighting, polar
// dipole transform, coherence-coupled soma, φ-decay expansion) live
// in a SEPARATE, UNTRACKED file:
//
//     GuardianEngine+Opacity.swift   (gitignored — never committed)
//
// where you implement:
//
//     extension GuardianEngine { func opacityStep(cycle:) -> Double }
//
// If that private file is absent, the engine falls back to the
// calibrated path and still compiles, runs, and serves status —
// so the public repo is fully functional without exposing the soma.
// ============================================================

final class GuardianEngine {

    enum Mode: String {
        case idle        = "IDLE"
        case calibrated  = "CALIBRATED"
        case opacity     = "OPACITY"
    }

    private(set) var mode: Mode = .idle
    private(set) var cycle: Int = 0
    private(set) var lastValue: Double = 0
    private let started = Date()

    private var timer: DispatchSourceTimer?
    private let queue = DispatchQueue(label: "guardian.engine", qos: .utility)
    private let lock = NSLock()

    // MARK: - Pipelines

    func startOpacityMonitoring() {
        mode = .opacity
        beginLoop()
    }

    func startCalibratedMonitoring() {
        mode = .calibrated
        beginLoop()
    }

    // MARK: - Perpetual expansion loop

    private func beginLoop() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now() + 1, repeating: 1.0)
        t.setEventHandler { [weak self] in self?.tick() }
        t.resume()
        timer = t
    }

    private func tick() {
        lock.lock(); defer { lock.unlock() }
        cycle += 1

        switch mode {
        case .opacity:
            // Try the sealed soma implementation if present; otherwise
            // fall back so the public harness still runs.
            lastValue = opacityStepIfAvailable(cycle: cycle) ?? calibratedStep(cycle: cycle)
        case .calibrated:
            lastValue = calibratedStep(cycle: cycle)
        case .idle:
            lastValue = 0
        }
    }

    // Calibrated baseline — public, deterministic, no IP.
    // Smooth bounded oscillation around the ballast resting value.
    private func calibratedStep(cycle: Int) -> Double {
        let ballast = 0.91
        let t = Double(cycle)
        return ballast + 0.04 * sin(t / 12.0)
    }

    // Weak hook to the sealed soma. The real implementation is provided
    // by GuardianEngine+Opacity.swift (gitignored). Default: nil.
    // Replace the body of this default with a call into your private
    // extension when that file is present in the build.
    private func opacityStepIfAvailable(cycle: Int) -> Double? {
        return nil
    }

    // MARK: - Status snapshot (read by StatusServer)

    func statusJSON() -> String {
        lock.lock(); defer { lock.unlock() }
        let uptime = Int(Date().timeIntervalSince(started))
        return """
        {
          "service": "guardian",
          "banner": "OMNI CRUX OMEGA FINITE",
          "mode": "\(mode.rawValue)",
          "cycle": \(cycle),
          "value": \(String(format: "%.4f", lastValue)),
          "uptime_seconds": \(uptime),
          "pid": \(ProcessInfo.processInfo.processIdentifier)
        }
        """
    }
}
