// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Vault",
    platforms: [.macOS(.v14)],
    dependencies: [
        // 积木规范化模板（规格 v0.1 §1.1）：本地 SPM 包，编译期共享令牌 / 组件 / 窗口与弹层契约。
        // 跨仓相对路径：要求 Shadeling 仓位于 ~/Dev/Shadeling，换机器需保持同布局
        //（package_app.sh 步骤 1 已加依赖前置检查兜底）。
        .package(path: "../../../../Shadeling/app/packages/BrickUIKit"),
    ],
    targets: [
        .executableTarget(
            name: "Vault",
            dependencies: [
                .product(name: "BrickUIKit", package: "BrickUIKit"),
            ],
            path: "Sources/Vault",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        )
    ]
)
