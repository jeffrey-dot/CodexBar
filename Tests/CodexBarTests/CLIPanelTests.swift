import CodexBarCore
import Commander
import Testing
@testable import CodexBarCLI

@Suite
struct CLIPanelTests {
    @Test
    func panelLineIncludesPrimarySecondaryAndCredits() {
        let payload = ProviderPayload(
            provider: .codex,
            account: nil,
            version: nil,
            source: "cli",
            status: nil,
            usage: UsageSnapshot(
                primary: .init(usedPercent: 30, windowMinutes: 300, resetsAt: nil, resetDescription: nil),
                secondary: .init(usedPercent: 55, windowMinutes: 10080, resetsAt: nil, resetDescription: nil),
                tertiary: nil,
                updatedAt: Date()),
            credits: CreditsSnapshot(remaining: 42, events: [], updatedAt: Date()),
            antigravityPlanInfo: nil,
            openaiDashboard: nil,
            error: nil)

        let line = CodexBarCLI.renderPanelLine(payloads: [payload], separator: " | ", includeProviderName: true)
        #expect(line.contains("Codex 70%/45%"))
        #expect(line.contains("$42"))
    }

    @Test
    func panelLineUsesErrorMarkerWhenFetchFails() {
        let payload = ProviderPayload(
            provider: .claude,
            account: nil,
            version: nil,
            source: "cli",
            status: nil,
            usage: nil,
            credits: nil,
            antigravityPlanInfo: nil,
            openaiDashboard: nil,
            error: CodexBarCLI.makeErrorPayload(code: .failure, message: "boom", kind: .provider))

        let line = CodexBarCLI.renderPanelLine(payloads: [payload], separator: " | ", includeProviderName: true)
        #expect(line == "Claude ERR")
    }

    @Test
    func panelParsesSeparatorAndShowProviderFlags() throws {
        let signature = CodexBarCLI._panelSignatureForTesting()
        let parser = CommandParser(signature: signature)
        let parsed = try parser.parse(arguments: ["--separator", " • ", "--show-provider"])
        #expect(parsed.options["separator"] == [" • "])
        #expect(parsed.flags.contains("showProvider"))
    }
}
