// Нативное окно для PDF2Text.
//
// Интерфейс — та же веб-страница, что и в браузерном режиме; меняется только то,
// что её рисует. WKWebView берёт движок из macOS, поэтому обёртка почти ничего
// не весит и не тянет ни Rust, ни Node.
//
// Сборка: swiftc -O desktop/PDF2Text.swift -o <bundle>/Contents/MacOS/PDF2Text

import Cocoa
import WebKit

private let portRange = 8765...8789
private let startupTimeout = 40.0

/// Через сколько секунд ожидания объяснить, почему так долго. Обычный запуск
/// укладывается в треть секунды, и подпись мелькает незамеченной. Долгим бывает
/// только первый запуск после установки: macOS сканирует незнакомое приложение
/// (замерено — около 11 секунд), результат кешируется на эту копию.
private let slowStartupHint = 3.0

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private var port = portRange.lowerBound
    private var waited = 0.0
    private var signalSources: [DispatchSourceSignal] = []
    private var hintShown = false
    private let status = NSTextField(labelWithString: "Запускаю PDF2Text…")

    func applicationDidFinishLaunching(_ notification: Notification) {
        port = firstFreePort()
        buildMenu()
        buildWindow()
        startServer()
        trapSignals()
        pollUntilReady()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // Сервер не должен пережить приложение: иначе останется висеть процесс
    // с занятым портом и открытыми документами пользователя.
    func applicationWillTerminate(_ notification: Notification) {
        server?.terminate()
    }

    /// `applicationWillTerminate` срабатывает только на штатный выход (Cmd+Q,
    /// закрытие окна). На SIGTERM/SIGINT — например `kill` или остановка из
    /// отладчика — он не вызывается, и бэкенд оставался жить сиротой.
    private func trapSignals() {
        for number in [SIGTERM, SIGINT] {
            signal(number, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
            source.setEventHandler { [weak self] in
                self?.server?.terminate()
                NSApp.terminate(nil)
            }
            source.resume()
            signalSources.append(source)
        }
    }

    // MARK: - Порт

    /// Первый свободный порт: два запущенных экземпляра не должны драться.
    private func firstFreePort() -> Int {
        for candidate in portRange {
            let handle = socket(AF_INET, SOCK_STREAM, 0)
            if handle < 0 { continue }
            var yes: Int32 = 1
            setsockopt(handle, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
            var addr = sockaddr_in()
            addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_port = UInt16(candidate).bigEndian
            addr.sin_addr.s_addr = inet_addr("127.0.0.1")
            let bound = withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    // Darwin. обязателен: без него Swift видит одноимённый метод NSObject.
                    Darwin.bind(handle, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            close(handle)
            if bound == 0 { return candidate }
        }
        return portRange.lowerBound
    }

    // MARK: - Сервер

    private func startServer() {
        // Сборка PyInstaller — onedir: в Resources лежит каталог pdf2text-server,
        // а исполняемый файл внутри него. Onefile стартовал 10–12 секунд, потому
        // что каждый раз распаковывал себя во временный каталог.
        guard let binary = Bundle.main.resourceURL?
            .appendingPathComponent("pdf2text-server")
            .appendingPathComponent("pdf2text-server") else {
            fail("В бандле нет pdf2text-server.")
            return
        }
        let process = Process()
        process.executableURL = binary
        var environment = ProcessInfo.processInfo.environment
        environment["PDF2TEXT_PORT"] = String(port)
        process.environment = environment
        do {
            try process.run()
            server = process
        } catch {
            fail("Не удалось запустить бэкенд: \(error.localizedDescription)")
        }
    }

    private func pollUntilReady() {
        guard let health = URL(string: "http://127.0.0.1:\(port)/api/v1/health") else { return }
        var request = URLRequest(url: health)
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let ready = data != nil
            DispatchQueue.main.async {
                if ready {
                    self.status.isHidden = true
                    self.webView.isHidden = false
                    self.webView.load(URLRequest(url: URL(string: "http://127.0.0.1:\(self.port)/")!))
                    return
                }
                self.waited += 0.25
                if self.waited > startupTimeout {
                    self.fail("Бэкенд не ответил за \(Int(startupTimeout)) секунд.")
                    return
                }
                if self.waited > slowStartupHint && !self.hintShown {
                    self.hintShown = true
                    self.status.stringValue = """
                        Запускаю PDF2Text…

                        Первый запуск после установки занимает 10–30 секунд:
                        macOS проверяет новое приложение. Дальше оно
                        открывается мгновенно.
                        """
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.pollUntilReady() }
            }
        }.resume()
    }

    private func fail(_ message: String) {
        status.isHidden = false
        status.stringValue = message
        webView?.isHidden = true
    }

    // MARK: - Окно

    private func buildWindow() {
        let frame = NSRect(x: 0, y: 0, width: 1180, height: 780)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "PDF2Text"
        window.minSize = NSSize(width: 860, height: 560)
        window.center()
        window.setFrameAutosaveName("PDF2TextMain")

        let configuration = WKWebViewConfiguration()
        // Страница узнаёт, что открыта в приложении, а не в браузере: в окне свой
        // заголовок уже есть, дублировать его в тулбаре не нужно.
        let marker = WKUserScript(
            source: "document.documentElement.dataset.shell = 'mac';",
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        configuration.userContentController.addUserScript(marker)

        webView = WKWebView(frame: frame, configuration: configuration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.isHidden = true
        // Страница сама рисует свой фон; без этого при старте мелькает белое.
        webView.setValue(false, forKey: "drawsBackground")

        status.frame = frame
        status.alignment = .center
        status.autoresizingMask = [.width, .height]
        status.textColor = .secondaryLabelColor
        // Подсказка про долгий первый запуск занимает несколько строк.
        status.usesSingleLineMode = false
        status.maximumNumberOfLines = 0
        status.cell?.wraps = true

        let content = NSView(frame: frame)
        content.addSubview(status)
        content.addSubview(webView)
        window.contentView = content
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "О программе PDF2Text", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Скрыть PDF2Text", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Выйти", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        // Без этого меню не работают Cmd+C и Cmd+V внутри веб-страницы.
        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "Правка")
        editMenu.addItem(withTitle: "Отменить", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "Вырезать", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Копировать", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Вставить", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Выбрать всё", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        main.addItem(editItem)

        NSApp.mainMenu = main
    }
}

// MARK: - Скачивание результата

extension AppDelegate: WKUIDelegate {
    /// `<input type="file">` внутри WKWebView сам панель выбора не открывает —
    /// без этого метода кнопка «Выбрать файл» не делает ничего.
    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.message = "Выберите PDF или изображение"
        panel.begin { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }
}

extension AppDelegate: WKNavigationDelegate, WKDownloadDelegate {
    /// Кнопки «Markdown» и «TXT» отдают blob-ссылки. WKWebView по умолчанию
    /// такую навигацию просто игнорирует — без этого файлы не сохраняются.
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        let scheme = navigationAction.request.url?.scheme ?? ""
        if scheme == "blob" || navigationAction.shouldPerformDownload {
            decisionHandler(.download)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping (URL?) -> Void
    ) {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        var target = downloads.appendingPathComponent(suggestedFilename)
        var index = 1
        let name = target.deletingPathExtension().lastPathComponent
        let ext = target.pathExtension
        while FileManager.default.fileExists(atPath: target.path) {
            let candidate = ext.isEmpty ? "\(name) \(index)" : "\(name) \(index).\(ext)"
            target = downloads.appendingPathComponent(candidate)
            index += 1
        }
        completionHandler(target)
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
