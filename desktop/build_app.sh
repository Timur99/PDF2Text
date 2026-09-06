#!/bin/bash
# Собирает PDF2Text.app и PDF2Text-<версия>.dmg вокруг замороженного бэкенда.
#
# Промежуточный вариант до Tauri: приложение поднимает локальный сервер и
# открывает браузер по умолчанию. Когда появится Tauri, тот же sidecar-бинарь
# переедет в его бандл без изменений.
#
# Запускать из корня репозитория: ./desktop/build_app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${PDF2TEXT_VERSION:-0.1.0}"
BUNDLE_ID="${PDF2TEXT_BUNDLE_ID:-com.pdf2text.desktop}"
APP="desktop/dist/PDF2Text.app"
SERVER="desktop/dist/pdf2text-server"

if [ ! -x "$SERVER" ]; then
  echo "Нет бинаря бэкенда. Сначала:"
  echo "  .venv/bin/pyinstaller desktop/pdf2text.spec --noconfirm --distpath desktop/dist --workpath desktop/build"
  exit 1
fi

echo "==> Собираю $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$SERVER" "$APP/Contents/Resources/pdf2text-server"
[ -f desktop/icons/AppIcon.icns ] && cp desktop/icons/AppIcon.icns "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>PDF2Text</string>
  <key>CFBundleDisplayName</key><string>PDF2Text</string>
  <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleExecutable</key><string>PDF2Text</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
  <!-- Бэкенд свой и локальный, но ATS по умолчанию режет любой http:// -->
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <!-- Apple Vision распознаёт русский начиная с macOS 13 -->
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

echo "==> Компилирую оболочку (Swift + WKWebView)"
swiftc -O desktop/PDF2Text.swift -o "$APP/Contents/MacOS/PDF2Text"
chmod +x "$APP/Contents/MacOS/PDF2Text"

echo "==> Собираю DMG"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="desktop/dist/PDF2Text-${VERSION}.dmg"
rm -f "$DMG"
hdiutil create -volname "PDF2Text" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo
echo "Готово:"
echo "  $APP  ($(du -sh "$APP" | cut -f1))"
echo "  $DMG  ($(du -sh "$DMG" | cut -f1))"
echo
echo "Окно нативное (WKWebView), браузер не открывается."
echo "Сборка неподписанная. При первом запуске macOS 15 покажет предупреждение:"
echo "  Системные настройки → Конфиденциальность и безопасность → «Всё равно открыть»."
