// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WeChatMP",
    platforms: [
        .macOS("15.0")
    ],
    products: [
        .executable(name: "WeChatMP", targets: ["WeChatMP"])
    ],
    targets: [
        .executableTarget(
            name: "WeChatMP",
            path: "Sources/WeChatMP"
        )
    ]
)
