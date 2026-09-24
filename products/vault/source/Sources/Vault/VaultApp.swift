import SwiftUI

@main
struct VaultApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 760, minHeight: 520)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 980, height: 680)
    }
}
