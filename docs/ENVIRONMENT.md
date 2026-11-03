# ENVIRONMENT.md — как поднять среду на своей машине

Документ отвечает на вопрос «что поставить и как проверить». Различия между платформами
собраны в `PLATFORMS.md`; здесь — последовательность шагов и разбор проблем.

Проверенная автором конфигурация: **Windows 10/11 x64 + DaVinci Resolve Studio 21.1.1 +
ffmpeg 9.x + Python 3.14 + Node 24**. Для macOS инструкции эквивалентны, но живой прогон
инструментов на macOS не выполнялся — это отмечено честно и не является «почти то же самое».

---

## Шаг 0. Что вообще должно стоять

| Компонент | Зачем | Версия |
|---|---|---|
| DaVinci Resolve (Studio) | монтаж, цвет, звук, рендер | 21.x проверено; 18+ допустимо с оговорками |
| Python | все инструменты | 3.9+ (проверено 3.14) |
| ffmpeg + ffprobe | перекодирование, замеры, извлечение кадров | 7+ (проверено 9.0.1) |
| Node.js | генерация DRX | 18+ (проверено 24) |
| Модули Python | numpy, opencv-python, pillow, faster-whisper | актуальные |

Модули Python ставятся одной командой:

```bash
pip install numpy opencv-python pillow faster-whisper
```

`faster-whisper` тянет ~2 ГБ моделей при первом скачивании — это нормально.

---

## Шаг 1. Поставить базу

### Windows

```powershell
winget install Gyan.FFmpeg
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
```

DaVinci Resolve — обычная установка с сайта Blackmagic или портативная сборка.
Портативная сборка запускается через `ResolvePortable.exe` (он поднимает нужные
службы); прямой запуск `Resolve.exe` внутри может не сработать.

### macOS

```bash
brew install ffmpeg
brew install python@3.12
brew install node
```

DaVinci Resolve — официальный пакет Blackmagic в `/Applications`.
Если Gatekeeper блокирует запуск: правый клик по иконке → «Открыть».
Для Python-скриптов, скачанных из интернета: `xattr -d com.apple.quarantine <файл>`.

---

## Шаг 2. Проверить

```bash
python tools/doctor.py
```

Что он проверяет и что означают статусы:

| Строка | Что значит |
|---|---|
| `[ok] python` | версия ≥ 3.9 |
| `[ok] python-модули` | numpy, cv2, PIL, faster-whisper на месте |
| `[ok] ffmpeg` | найден и запускается (показывает версию) |
| `[ok] ffprobe` | нужен для замеров потоков |
| `[ok] resolve` | исполняемый файл найден |
| `[ok] resolve-процесс` | Resolve **запущен** (иначе скриптовый API недоступен) |
| `[ok] resolve-scripting-api` | внешняя папка модулей найдена |
| `[ok] lut-dir` | папка LUT Resolve существует |
| `[ok] node` | Node для DRX |
| `[ok] vendor-кодеки` | DRX-кодек на месте |
| `[ok] npm-зависимости` | zstd-codec и fzstd установлены |
| `[warn] disk` | мало места под превью и рендеры |
| `[warn] sfxmint-ключ` | генерация звуков закрыта, библиотека CC0 доступна |

Код возврата: `0` — можно работать, `1` — есть блокирующие провалы.

---

## Шаг 3. Зафиксировать пути

```bash
python tools/env_paths.py set src_root    "D:/Shoot/raw"
python tools/env_paths.py set project_root "D:/Shoot/project"
python tools/env_paths.py set work_root   "D:/Shoot/project/work"
python tools/env_paths.py show
```

Правило приоритета: **переменная окружения `ZOVOD_*` > `config/env.json` > автодетект**.
Файл `config/env.json` — обычный JSON, его можно править руками и хранить рядом с
проектом (не коммитить в публичный репозиторий, если пути чувствительные).

Полезно знать: автодетект Resolve на Windows умеет находить **портативные сборки**
в `~/Downloads`, `~/Tools`, `~/Desktop`. Если Resolve установлен нестандартно —
укажи путь явно.

---

## Шаг 4. Подключить агента к Resolve

Два рабочих канала. Выбери любой (или оба).

### A. Мост через скриптовый API (рекомендуется для агента без MCP)

```bash
python skills/davinci-resolve-workbench/scripts/resolve_doctor.py
python skills/davinci-resolve-workbench/scripts/resolve_bridge.py script мой_скрипт.py --unsafe --timeout=300
```

`--unsafe` нужен для скриптов, которые читают файлы или пишут на диск; обычный режим
безопасно ограничен песочницей. Про `--unsafe` стоит проговаривать заказчику.

### B. MCP-сервер Resolve

Если агент умеет MCP — подключи сервер и используй его инструменты. Список и
возможности: `skills/davinci-resolve-workbench/SKILL.md` и `references/`.

### Что должно быть включено в самом Resolve

* DaVinci Resolve **Studio** — нужен для DRX и части API (в бесплатной версии
  ограничения).
* В настройках: *System → General → External scripting using local network* —
  для внешнего скриптового API.
* Модули `DaVinciResolveScript.py` должны лежать в системной папке модулей
  (путь — в таблице `PLATFORMS.md`).

---

## Шаг 5. Папка LUT

LUT-ы берутся **из локальной установки Resolve**, а не из чужих сборок:

* Windows: `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT`
* macOS: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT`

Свои LUT генерируются `tools/color/make_luts.py` и кладутся в эту папку; после копирования
в Resolve нужно обновить список LUT в интерфейсе (или перезапустить Resolve).

---

## Шаг 6. Зависимости вендорных кодеков

Для офлайн-генерации DRX нужен Node и две npm-библиотеки:

```bash
cd vendor
npm install
```

Установятся `zstd-codec` и `fzstd` (обе MIT). Без них `tools/color/make_drx.js`
упадёт с ошибкой загрузки модуля — это ожидаемо и лечится одной командой выше.

---

## Шаг 7. Создать рабочий проект

```bash
python tools/new_project.py "НазваниеПроекта" --src "D:/Shoot/raw" --fps 25
```

Скрипт создаёт структуру папок проекта, конфиг проверки и копию шаблона контекста.
Структуру можно править руками — это просто папки.

---

## Разбор проблем

| Симптом | Причина | Что делать |
|---|---|---|
| `doctor` не находит ffmpeg | не в PATH | переустановить / указать в `env.json` ключ `ffmpeg` |
| Resolve найден, но «не отвечает на скрипты» | Resolve не запущен или открыт модальный диалог | запустить Resolve; закрыть модалки `tools/dismiss_dialogs.py` |
| `ImportMedia` ничего не импортирует | передан список вместо строки | передавать **строку** пути (баг API, см. `docs/RESOLVE_RECIPE.md`) |
| скрипт внутри Resolve падает с `SyntaxError` на первой строке | в файле BOM | перезаписать без BOM (`utf-8`, не `utf-8-sig`) |
| `node make_drx.js` → `Cannot find module 'zstd-codec'` | не установлены npm-зависимости | `cd vendor && npm install` |
| файлы читаются с кракозябрами | кодировка | читать `utf-8-sig`, писать `utf-8` |
| macOS: агент «не видит» исходники | нет разрешения на папку | *Системные настройки → Конфиденциальность → Файлы и папки* |
| macOS: Python 3.9 из системы, нет `pip install` | системный Python защищён | `brew install python@3.12` и работать через `python3.12` |
| Resolve падает при применении DRX | самописный/кривой DRX | использовать вендорный кодек (`tools/color/make_drx.js`), он проверен |

---

## Что осталось непроверенным

* Живой прогон всех инструментов на **macOS** — не выполнялся.
* Версии Resolve, отличные от 21.1.1, — поведение API может отличаться; сверяйся с
  `docs/RESOLVE_RECIPE.md` и при расхождениях — фиксируй в контексте проекта.
* Рендер-джобы и Fusion-композиции — проверяются только в самом Resolve, не скриптом.
