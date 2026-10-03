#!/bin/bash
# Собирает PDF2Text.app и PDF2Text-<версия>.dmg вокруг замороженного бэкенда.
#
# Приложение поднимает локальный сервер и открывает нативное окно WKWebView.
#
# Запускать из корня репозитория: ./desktop/build_app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${PDF2TEXT_VERSION:-0.1.1}"
BUNDLE_ID="${PDF2TEXT_BUNDLE_ID:-com.pdf2text.desktop}"
SIGN_IDENTITY="${PDF2TEXT_SIGN_IDENTITY:--}"
NOTARY_PROFILE="${PDF2TEXT_NOTARY_PROFILE:-}"
PYTHON="${PDF2TEXT_PYTHON:-.venv/bin/python}"
APP="desktop/dist/PDF2Text.app"
SERVER="desktop/dist/pdf2text-server"

if [ -n "$NOTARY_PROFILE" ] && [ "$SIGN_IDENTITY" = "-" ]; then
  echo "Для нотаризации задайте PDF2TEXT_SIGN_IDENTITY (Developer ID Application)." >&2
  exit 1
fi

if [ ! -d "$SERVER" ]; then
  echo "Нет бинаря бэкенда. Сначала:"
  echo "  .venv/bin/pyinstaller desktop/pdf2text.spec --noconfirm --distpath desktop/dist --workpath desktop/build"
  exit 1
fi

echo "==> Собираю $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
# Сборка onedir: копируем каталог целиком. Исполняемый файл внутри —
# Resources/pdf2text-server/pdf2text-server, именно его запускает оболочка.
cp -R "$SERVER" "$APP/Contents/Resources/pdf2text-server"
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
mkdir -p desktop/build/ModuleCache
swiftc -O -module-cache-path desktop/build/ModuleCache \
  desktop/PDF2Text.swift -o "$APP/Contents/MacOS/PDF2Text"
chmod +x "$APP/Contents/MacOS/PDF2Text"

echo "==> Подписываю и проверяю приложение"
"$PYTHON" desktop/sign_app.py "$APP" --identity "$SIGN_IDENTITY"

echo "==> Собираю DMG"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
# Проверяем также копию, которая фактически попадёт в образ.
"$PYTHON" desktop/sign_app.py "$STAGE/PDF2Text.app" --verify-only
ln -s /Applications "$STAGE/Applications"
DMG="desktop/dist/PDF2Text-${VERSION}.dmg"
rm -f "$DMG"
hdiutil create -volname "PDF2Text" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

if [ "$SIGN_IDENTITY" != "-" ]; then
  codesign --force --sign "$SIGN_IDENTITY" --timestamp "$DMG"
  codesign --verify --strict "$DMG"
fi
if [ -n "$NOTARY_PROFILE" ]; then
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
fi
hdiutil verify "$DMG"
shasum -a 256 "$DMG" > "$DMG.sha256"

echo
echo "Готово:"
echo "  $APP  ($(du -sh "$APP" | cut -f1))"
echo "  $DMG  ($(du -sh "$DMG" | cut -f1))"
echo
echo "Окно нативное (WKWebView), браузер не открывается."
if [ -n "$NOTARY_PROFILE" ]; then
  echo "Developer ID: образ подписан и нотаризован, билет прикреплён."
else
  echo "Подпись проверена, но нотаризации нет. Gatekeeper может блокировать запуск."
  echo "Инструкция для доверенной тестовой сборки: desktop/README.md → Подпись и Gatekeeper."
fi
