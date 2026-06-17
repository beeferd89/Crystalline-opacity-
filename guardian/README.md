# Guardian (headless daemon)

The Mac Mini M4 vault-node daemon for Kibler AI Solutions Corp.
Public harness — the CrystallineOpacity math is sealed out via `.gitignore`.

> This is a self-contained SwiftPM package living in the `guardian/`
> subdirectory of the repo. Run all commands below from inside `guardian/`.

## Build & run
```bash
cd guardian
swift build -c release
swift run guardian --headless --opacity --port 8547
```

Then, in another terminal:
```bash
curl localhost:8547/status
```

## Flags
- `--headless` — run as daemon (required for LaunchAgent keepalive)
- `--opacity`  — enable crystalline-soma pipeline (φ-basis). Omit for calibrated-only.
- `--port N`   — status endpoint port (default 8547)

## Files
| File | Role |
|------|------|
| `Package.swift` | SwiftPM executable manifest (macOS 13+) |
| `Sources/guardian/main.swift` | Entry shim — dispatches headless vs usage |
| `Sources/guardian/GuardianHeadless.swift` | Daemon loop, banner, log rotation |
| `Sources/guardian/GuardianEngine.swift` | Public harness — cycle loop, state, status JSON |
| `Sources/guardian/StatusServer.swift` | Read-only HTTP `/status` endpoint (BSD sockets) |
| `com.kibler.guardian.plist` | LaunchAgent — boot on login, KeepAlive |
| `.gitignore` | Seals the patented soma math out of the repo |

## The sealed soma
The four novel patent elements (φ-spiral basis, polar dipole transform,
coherence-coupled soma, φ-decay expansion) are NOT in this repo. They go in:

    Sources/guardian/GuardianEngine+Opacity.swift   (gitignored)

implementing `func opacityStep(cycle:) -> Double`, then wire it into
`opacityStepIfAvailable(cycle:)`. Without that file the daemon falls back
to the calibrated path and still builds, runs, and serves status — so the
public repo is fully functional without exposing the IP.

## Install the LaunchAgent
```bash
# edit the binary path in the plist first, then:
cp com.kibler.guardian.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kibler.guardian.plist
launchctl list | grep guardian
```

## NOTE
Structure-verified and dependency-free, but compile it on the M4 — that
first `swift build` is the real confirmation. `StatusServer.swift` uses the
Darwin POSIX socket API, so it is macOS-only by design.
