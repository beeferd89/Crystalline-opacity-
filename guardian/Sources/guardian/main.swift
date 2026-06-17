import Foundation

// ============================================================
// GUARDIAN ENTRY POINT  (main.swift)
//
// This replaces the Xcode @main / SwiftUI dispatch with a plain
// executable entry. The original GuardianHeadless.swift was written
// for an Xcode app target and imported SwiftUI; a headless daemon
// launched by a LaunchAgent never draws UI, so this executable
// drops SwiftUI entirely and just runs the daemon.
//
//   --headless   run as daemon (required for LaunchAgent)
//   --opacity    enable crystalline-soma pipeline (φ-basis)
//   --port N     status HTTP port (default 8547)
// ============================================================

rotateLogsIfNeeded()

if detectLaunchMode() {
    runHeadlessDaemon()
} else {
    // No UI in this build. Print usage and exit cleanly.
    print("""
    Guardian (headless build)
    Usage: guardian --headless [--opacity] [--port <n>]

      --headless   Run as a perpetual daemon (LaunchAgent keepalive).
      --opacity    Enable crystalline-soma monitoring (φ-basis).
                   Omit for calibrated-only monitoring.
      --port <n>   Status endpoint port (default 8547).

    Example:
      guardian --headless --opacity --port 8547
    """)
}
