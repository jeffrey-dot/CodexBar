import CodexBarCore
import Commander
import Foundation

extension CodexBarCLI {
    static func runPanel(_ values: ParsedValues) async {
        let output = CLIOutputPreferences.from(values: values)
        let config = Self.loadConfig(output: output)
        let provider = Self.decodeProvider(from: values, config: config)
        let includeStatus = values.flags.contains("status")
        let showProvider = values.flags.contains("showProvider")
        let separator = values.options["separator"]?.last ?? " | "
        let sourceModeRaw = values.options["source"]?.last
        let parsedSourceMode = Self.decodeSourceMode(from: values)
        if sourceModeRaw != nil, parsedSourceMode == nil {
            Self.exit(
                code: .failure,
                message: "Error: --source must be auto|web|cli|oauth|api.",
                output: output,
                kind: .args)
        }
        let webTimeout = Self.decodeWebTimeout(from: values) ?? 60
        let verbose = values.flags.contains("verbose")
        let providerList = provider.asList

        let tokenSelection: TokenAccountCLISelection
        do {
            tokenSelection = try Self.decodeTokenAccountSelection(from: values)
        } catch {
            Self.exit(code: .failure, message: "Error: \(error.localizedDescription)", output: output, kind: .args)
        }

        if tokenSelection.allAccounts, tokenSelection.label != nil || tokenSelection.index != nil {
            Self.exit(
                code: .failure,
                message: "Error: --all-accounts cannot be combined with --account or --account-index.",
                output: output,
                kind: .args)
        }

        if tokenSelection.usesOverride {
            guard providerList.count == 1 else {
                Self.exit(
                    code: .failure,
                    message: "Error: account selection requires a single provider.",
                    output: output,
                    kind: .args)
            }
            guard TokenAccountSupportCatalog.support(for: providerList[0]) != nil else {
                Self.exit(
                    code: .failure,
                    message: "Error: \(providerList[0].rawValue) does not support token accounts.",
                    output: output,
                    kind: .args)
            }
        }

        #if !os(macOS)
        if parsedSourceMode?.usesWeb == true {
            Self.exit(
                code: .failure,
                message: "Error: --source web/auto is only supported on macOS.",
                output: output,
                kind: .runtime)
        }
        #endif

        let browserDetection = BrowserDetection()
        let fetcher = UsageFetcher()
        let claudeFetcher = ClaudeUsageFetcher(browserDetection: browserDetection)
        let tokenContext: TokenAccountCLIContext
        do {
            tokenContext = try TokenAccountCLIContext(
                selection: tokenSelection,
                config: config,
                verbose: verbose)
        } catch {
            Self.exit(code: .failure, message: "Error: \(error.localizedDescription)", output: output, kind: .config)
        }

        let command = UsageCommandContext(
            format: .json,
            includeCredits: true,
            sourceModeOverride: parsedSourceMode,
            antigravityPlanDebug: false,
            augmentDebug: false,
            webDebugDumpHTML: false,
            webTimeout: webTimeout,
            verbose: verbose,
            useColor: false,
            resetStyle: .countdown,
            jsonOnly: true,
            fetcher: fetcher,
            claudeFetcher: claudeFetcher,
            browserDetection: browserDetection)

        var payload: [ProviderPayload] = []
        var exitCode: ExitCode = .success
        for selectedProvider in providerList {
            let status = includeStatus ? await Self.fetchStatus(for: selectedProvider) : nil
            let output = await ProviderInteractionContext.$current.withValue(.background) {
                await Self.fetchUsageOutputs(
                    provider: selectedProvider,
                    status: status,
                    tokenContext: tokenContext,
                    command: command)
            }
            if output.exitCode != .success {
                exitCode = output.exitCode
            }
            payload.append(contentsOf: output.payload)
        }

        let includeProviderName = showProvider || payload.count > 1
        print(Self.renderPanelLine(payloads: payload, separator: separator, includeProviderName: includeProviderName))
        Self.exit(code: exitCode, output: output, kind: exitCode == .success ? .runtime : .provider)
    }

    static func renderPanelLine(
        payloads: [ProviderPayload],
        separator: String,
        includeProviderName: Bool) -> String
    {
        let segments = payloads.map { payload in
            self.renderPanelSegment(payload: payload, includeProviderName: includeProviderName)
        }
        return segments.joined(separator: separator)
    }

    private static func renderPanelSegment(payload: ProviderPayload, includeProviderName: Bool) -> String {
        let provider = ProviderDescriptorRegistry.cliNameMap[payload.provider]
        let providerLabel = provider.map { ProviderDescriptorRegistry.descriptor(for: $0).metadata.displayName } ?? payload.provider
        let providerPrefix = includeProviderName ? "\(providerLabel) " : ""

        if payload.error != nil {
            return providerPrefix + "ERR"
        }

        let primaryRemaining = payload.usage?.primary.map { Int($0.remainingPercent.rounded()) }
        let secondaryRemaining = payload.usage?.secondary.map { Int($0.remainingPercent.rounded()) }

        var usageText = "--"
        if let primaryRemaining, let secondaryRemaining {
            usageText = "\(primaryRemaining)%/\(secondaryRemaining)%"
        } else if let primaryRemaining {
            usageText = "\(primaryRemaining)%"
        } else if let secondaryRemaining {
            usageText = "w\(secondaryRemaining)%"
        }

        var segment = providerPrefix + usageText
        if payload.provider == UsageProvider.codex.rawValue, let credits = payload.credits {
            segment += " $\(UsageFormatter.creditsString(from: credits.remaining))"
        }
        if let marker = Self.statusMarker(for: payload.status?.indicator) {
            segment += " \(marker)"
        }
        return segment
    }

    private static func statusMarker(for indicator: ProviderStatusPayload.ProviderStatusIndicator?) -> String? {
        guard let indicator else { return nil }
        switch indicator {
        case .none:
            return nil
        case .minor:
            return "~"
        case .major:
            return "!"
        case .critical:
            return "!!"
        case .maintenance:
            return "M"
        case .unknown:
            return "?"
        }
    }
}
