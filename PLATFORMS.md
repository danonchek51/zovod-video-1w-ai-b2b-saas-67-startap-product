# PLATFORMS.md — Windows и macOS в одном пакете

Пакет один. Код — Python 3.9+ без платформенных зависимостей, пути не зашиты, а
вычисляются в `tools/env_paths.py`. Документ описывает, что различается и что нужно
доустановить.

---

## Краткая таблица

| Что | Windows | macOS |
|---|---|---|
| Resolve | `C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe`; портативные сборки — где угодно, ищутся в `~/Downloads`, `~/Tools`, `~/Desktop` | `/Applications/DaVinci Resolve.app/Contents/MacOS/Resolve` |
| Папка LUT | `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT` | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT` |
| Модули скриптового API | `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules` | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules` |
| ffmpeg | `winget install Gyan.FFmpeg` | `brew install ffmpeg` |
| Node | [nodejs.org](https://nodejs.org) (LTS) | `brew install node` |
| Python | `winget install Python.Python.3.12` | `brew install python@3.12` (системный 3.9 у Apple устарел) |
| Пути в командах | обратный слэш, диск `C:` | прямой слэш, `/Volumes/...` для внешних дисков |
| Разделитель в имени файла | `\` | `/` — в имени файла **нельзя** |
| Регистр имён | нечувствительный | **чувствительный**: `CLIP_A_cut.mp4` ≠ `clip_a_cut.mp4` |
| Портативная сборка Resolve | встречается часто (сборка «portable») | редко, обычно обычная установка |
| Закрытие модалок | `tools/dismiss_dialogs.py` (Win32) | `tools/dismiss_dialogs.py` (osascript) |

---

## Что одинаково

* Рецепты звука, грейда, монтажа, методика измерений — платформенно-независимы.
* Все пути берутся из `tools/env_paths.py`; ни один инструмент не хардкодит путь.
* API Resolve вызывается одинаково: через мост (`resolve_bridge.py`) или через MCP-сервер.
* Форматы отчётов, точки отката, чек-листы — одинаковые.

---

## Установка: Windows

```powershell
winget install Gyan.FFmpeg
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
# DaVinci Resolve — обычная установка или портативная сборка
```

Далее:

```powershell
python tools\doctor.py
python tools\env_paths.py set src_root "F:\Shoot\raw"
python tools\env_paths.py set project_root "F:\Shoot\project"
```

Если Resolve портативный (`Resolve.exe` глубоко в `~/Downloads`), найди его:
`python tools\env_paths.py set resolve_exe "<полный путь к Resolve.exe>"`.
В портативной сборке запуск идёт через лаунчер (`ResolvePortable.exe`) — он же умеет
поднимать нужные сервисы; обычный `Resolve.exe` внутри может не стартовать без него.

---

## Установка: macOS

```bash
brew install ffmpeg
brew install python@3.12
brew install node
# DaVinci Resolve — из официального пакета Blackmagic в /Applications
```

Далее:

```bash
python3 tools/doctor.py
python3 tools/env_paths.py set src_root "/Volumes/Macintosh HD/Shoot/raw"
python3 tools/env_paths.py set project_root "/Volumes/Macintosh HD/Shoot/project"
```

### Особенности macOS, о которых стоит знать заранее

1. **Разрешения.** macOS спрашивает доступ к папкам (Файлы и папки, «Полный доступ к
   диску»). Если агент не видит исходники — сначала выдай доступ в
   `Системные настройки → Конфиденциальность и безопасность → Файлы и папки`.
   Диск с камеры (`/Volumes/...`) тоже требует разрешения.
2. **Gatekeeper.** Скачанный Resolve из интернета может не запускаться: правый клик по
   иконке → «Открыть». Для скриптов Python: `xattr -d com.apple.quarantine <файл>`.
3. **Внешний скриптовый API.** В настройках Resolve: *Preferences → System → General →
   External scripting using local network* (в новых версиях путь называется иначе).
   Модули лежат в `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules`.
4. **Имена файлов.** macOS различает регистр, а Finder нормализует Unicode. Не полагайся
   на кириллицу и пробелы в именах файлов, которые уходят в Resolve.
5. **Права на запись в `/Library` и `/Applications`** нужны только при установке Resolve и
   при копировании LUT — обычный пользователь справится, через `sudo` не требуется.
6. **Рендер.** Кодировщики Resolve на macOS могут отсутствовать, если не установлены
   дополнительные компоненты; проверяй список доступных форматов до рендер-джоба.

---

## Проверенная конфигурация

| Параметр | Значение |
|---|---|
| ОС | Windows 10/11 x64 |
| Resolve | DaVinci Resolve **Studio** 21.1.1 (портативная сборка) |
| ffmpeg | 9.x |
| Python | 3.14 |
| Node | 24 |
| Проверено | 2026-11 |

**Честная оговорка.** Всё перечисленное проверено на Windows. Для macOS подготовлены
эквивалентные пути, команды и процедуры, но **живого прогона инструментов на macOS не
было**. Поэтому первый шаг получателя на macOS — `python3 tools/doctor.py`, а не
«просто начинаем». Если что-то поведёт себя иначе — это находка, её надо записать в
контекст проекта и починить инструмент, а не обойти молча.
