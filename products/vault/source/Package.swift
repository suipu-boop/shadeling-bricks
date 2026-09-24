// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Vault",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "Vault",
            path: "Sources/Vault",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        )
    ]
)
