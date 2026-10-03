# Desktop / DMG

Финальный артефакт для macOS — `.dmg` с приложением, которое поднимает
локальный backend на `127.0.0.1` и открывает тот же UI.

## Имя и идентификаторы

| Что | Значение |
|---|---|
| Отображаемое имя | `PDF2Text` |
| Bundle identifier | `com.<владелец>.pdf2text` |
| Файл образа | `PDF2Text-<версия>.dmg` |
| Иконка | `icons/AppIcon.icns` |

Регистр — `PDF2Text`, не `PDF2TEXT`: в `DESIGN.md` записано «регистр
предложения везде». Репозиторий с 13.09.2026 тоже называется `PDF2Text`
(был `local_OCR`); локальный каталог на диске переименован не был.

## Иконка

```bash
python desktop/make_icon.py
iconutil -c icns desktop/icons/AppIcon.iconset -o desktop/icons/AppIcon.icns
```

`iconutil` не работает под песочницей Claude Code — падает с
`Failed to generate ICNS` даже на корректном наборе. Запускать напрямую.

## Сборка

Два шага. Первый — бэкенд в самостоятельный бинарь, второй — бандл и образ.

```bash
.venv/bin/pyinstaller desktop/pdf2text.spec --noconfirm \
  --distpath desktop/dist --workpath desktop/build
./desktop/build_app.sh
```

На выходе `desktop/dist/PDF2Text.app`, `desktop/dist/PDF2Text-0.1.1.dmg`
и контрольная сумма `PDF2Text-0.1.1.dmg.sha256`.
Переменные: `PDF2TEXT_VERSION`, `PDF2TEXT_BUNDLE_ID`, `PDF2TEXT_PYTHON`
(по умолчанию `.venv/bin/python`), `PDF2TEXT_SIGN_IDENTITY`, `PDF2TEXT_NOTARY_PROFILE`.

**Onedir, а не onefile.** Первая сборка была onefile, и это стоило 10–12 секунд
на **каждом** запуске: однофайловый бинарь распаковывает себя во временный каталог,
прежде чем стартовать. Замер до и после — 10,2 с против 0,33 с. Расплата — бандл
вырос с 49 до 108 МБ (внутри каталог несжатых файлов вместо одного сжатого), но
в образе разница всего 50 → 55 МБ: DMG всё равно жмёт содержимое.

Внутри бандла лежит каталог `Resources/pdf2text-server/`, исполняемый файл —
`Resources/pdf2text-server/pdf2text-server`. Этот путь знают три места:
`pdf2text.spec` (секция `COLLECT`), `build_app.sh` (`cp -R`) и `PDF2Text.swift`
(`startServer`). Менять — во всех трёх сразу.

Первый запуск нового бинаря всё равно займёт ~10 секунд: macOS сканирует
незнакомый исполняемый файл. Результат кешируется, дальше 0,3 с.

**Почему 49 МБ, а не 400.** В `pdf2text.spec` главное — не то, что включено, а секция
`EXCLUDES`: paddle, paddlex, torch и прочий ML-стек в бандл не едут. Дефолтный движок —
Apple Vision, встроенный в macOS. Внутри бандла `/api/v1/engines` показывает
`paddleocr: available=false`, и это правильно: он остаётся опциональной докачкой.

PyInstaller пишет кеш в `~/Library/Application Support/pyinstaller`, под песочницей
Claude Code это не проходит — собирать напрямую.

Пути внутри spec считаются от самого spec-файла (`SPECPATH`), а не от текущего каталога.
Так было не всегда: с `pathex=[".."]` сборка из корня репозитория молча давала битый бинарь,
падавший на `ModuleNotFoundError: No module named 'backend'` только в момент запуска.

## Оболочка: Swift + WKWebView

`desktop/PDF2Text.swift` — нативное окно (~230 строк, бинарь 87 КБ). Рисует ту же страницу,
что и веб-версия, движком WebKit из самой macOS. Rust и Node не нужны, компиляция — секунды.

**Почему не Tauri.** Главное преимущество Tauri — кроссплатформенность, а продукт
macOS-only по построению: дефолтный движок Apple Vision больше нигде не существует.
Полтора гигабайта тулчейна ради портируемости, которой не воспользуемся. Tauri остаётся
опцией, если однажды откажемся от Vision или понадобится его экосистема.

Что делает оболочка:

- ищет свободный порт перебором 8765–8789 — два экземпляра не подерутся;
- запускает `pdf2text-server` из `Contents/Resources` и ждёт `/api/v1/health`;
- гасит бэкенд и на штатном выходе (`applicationWillTerminate`), и по SIGTERM/SIGINT
  (`DispatchSource`) — без второго бэкенд оставался сиротой с занятым портом;
- перехватывает blob-ссылки кнопок «Markdown» и «TXT» и сохраняет в «Загрузки»:
  WKWebView без `WKDownloadDelegate` такую навигацию просто игнорирует.

**Обязательное в Info.plist:** `NSAppTransportSecurity` → `NSAllowsLocalNetworking`.
Без него ATS режет `http://127.0.0.1` и окно остаётся пустым.

## Отладка

```bash
PDF2TEXT_LOG_LEVEL=info desktop/dist/PDF2Text.app/Contents/MacOS/PDF2Text
```

Запуск бинаря напрямую, не через `open`, отдаёт логи в терминал. По умолчанию уровень
`warning`: в собранном приложении логи уходят в системный журнал, и содержимого документов
там быть не должно.

## Раздача

`.dmg` собирается локально и в репозиторий не попадает: игнорируется строками
`*.dmg` и `desktop/dist/` в `.gitignore`. Пятьдесят мегабайт в истории git — это
навсегда, а GitHub предупреждает уже на 50 МБ и отказывает на 100 МБ.

Канал раздачи — GitHub Release, куда образ прикладывается как asset:

```bash
git tag v0.1.1 && git push origin v0.1.1
gh release create v0.1.1 desktop/dist/PDF2Text-0.1.1.dmg \
  desktop/dist/PDF2Text-0.1.1.dmg.sha256 \
  --title "PDF2Text 0.1.1" --notes-file docs/RELEASE-v0.1.1.md
```

Без `gh` — то же самое через веб: Releases → Draft a new release → перетащить файл.

Пока нет Developer ID и нотаризации, к релизу прилагается инструкция первого
запуска из `docs/RELEASE-v0.1.1.md`. Точный текст предупреждения зависит от macOS.

## Подпись и Gatekeeper

В 0.1.0 у оболочки была только подпись компоновщика, без ресурсов `.app`.
Проверка приложения и вложенного `Python.framework` выдавала
`code has no resources but signature indicates they must be present`.
Это отдельная ошибка целостности сборки, а не просто отсутствие Developer ID.

Начиная с 0.1.1, `sign_app.py` подписывает все Mach-O-файлы бэкенда, затем
вложенные framework/bundle и последним готовое приложение. Подпись выполняется
изнутри наружу, без `codesign --deep` при подписании. Каждый компонент проверяется
отдельно, поскольку код в `Resources` может не попасть в рекурсивную проверку.
Сборка останавливается при ошибке; перед упаковкой также проверяется копия
приложения, помещаемая в DMG. После упаковки проверяется сам образ.

| Вариант | Что обеспечивает |
|---|---|
| Ad-hoc (по умолчанию, бесплатно) | Валидная подпись и контроль целостности; Gatekeeper всё ещё может блокировать скачанное приложение |
| Developer ID без нотаризации | Подтверждение разработчика; этого недостаточно для обычного распространения без предупреждений |
| Developer ID + нотаризация | Путь распространения с проверкой Apple и прикреплённым билетом |

### Пробный запуск доверенной сборки

Перетащите приложение из DMG в «Программы». Если macOS предлагает
«Всё равно открыть» в **Системные настройки → Конфиденциальность и безопасность**,
можно воспользоваться этой кнопкой. Её наличие для ad-hoc сборки не гарантируется.

Если запуск заблокирован, сначала проверьте подпись установленной копии:

```bash
codesign --verify --deep --strict --verbose=2 /Applications/PDF2Text.app
```

Если проверка завершается с ошибкой, не обходите её: заново скачайте исправленную
сборку и замените старое приложение. Для сборки, полученной от доверенного
разработчика, после успешной проверки можно снять карантин только с PDF2Text:

```bash
xattr -dr com.apple.quarantine /Applications/PDF2Text.app
open /Applications/PDF2Text.app
```

Эта команда отключает проверку карантина для данного приложения, а не чинит его
подпись. Ad-hoc подпись сама по себе не подтверждает личность разработчика.

### Developer ID и нотаризация

Нужны сертификат **Developer ID Application** с закрытым ключом в Keychain и
профиль учётных данных `notarytool`, заранее сохранённый в Keychain.
Секреты не передаются в исходниках или переменных сборки.

```bash
PDF2TEXT_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)' \
PDF2TEXT_NOTARY_PROFILE='pdf2text-notary' \
./desktop/build_app.sh
```

Для Developer ID скрипт включает hardened runtime и timestamp, подписывает DMG,
отправляет его на нотаризацию, прикрепляет и проверяет билет. Нотаризуется образ;
локальная `.app` вне образа отдельного прикреплённого билета не получает.
Этот режим требует проверки на реальном сертификате; ad-hoc сборка не проверяет
совместимость бэкенда с hardened runtime.

Проверка установленной сборки перед публикацией:

```bash
.venv/bin/python desktop/sign_app.py /Applications/PDF2Text.app --verify-only
spctl --assess --type execute --verbose=2 /Applications/PDF2Text.app
xcrun stapler validate desktop/dist/PDF2Text-0.1.1.dmg
```

Для ad-hoc сборки отказ `spctl` и отсутствие билета ожидаемы. Они не означают,
что `codesign` должен выдавать ошибку целостности.

Справка: [Apple — Code Signing In Depth](https://developer.apple.com/library/archive/technotes/tn2206/),
[Apple — Notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).
