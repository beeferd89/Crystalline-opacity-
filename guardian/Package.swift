// swift-tools-version: 5.9
// Guardian — headless daemon for the Mac Mini M4 vault node.
// Executable SwiftPM target (NOT a library, NOT an Xcode app bundle).
// Build:  swift build -c release
// Run:    swift run guardian --headless --opacity --port 8547

import PackageDescription

let package = Package(
    name: "Guardian",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "guardian",
            path: "Sources/guardian"
        )
    ]
)
