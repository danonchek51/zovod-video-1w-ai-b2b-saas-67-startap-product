# Быстрый старт — macOS

Для машин на macOS. Полная версия — `docs/ENVIRONMENT.md`, различия платформ —
`PLATFORMS.md`.

> **Честная оговорка.** Инструменты пакета разрабатывались и проверялись на Windows.
> Для macOS подготовлены пути, команды и процедуры, но **живого прогона не было**.
> Первый шаг — `doctor.py`, и любые расхождения записывай в контекст проекта.

## 1. Проверить, что всё на месте

```bash
python3 tools/doctor.py
```

Если `python3` указывает на системный 3.9 — поставь свежий:

```bash
brew install python@3.12
python3.12 tools/doctor.py
```

## 2. Поставить недостающее

```bash
brew install ffmpeg
brew install node
python3.12 -m pip install numpy opencv-python pillow faster-whisper
```

DaVinci Resolve — официальный пакет Blackmagic в `/Applications`.

## 3. Разрешения macOS

Если агент «не видит» исходники:

* *Системные настройки → Конфиденциальность и безопасность → Файлы и папки* →
  разрешить доступ к нужным папкам;
* внешний диск (`/Volumes/...`) — добавить в *Диски и тома*;
* для скриптов, скачанных из интернета: `xattr -d com.apple.quarantine <файл>`;
* Resolve, скачанный из интернета: правый клик по иконке → «Открыть».

## 4. Указать свои пути

```bash
python3 tools/env_paths.py set src_root    "/Volumes/Macintosh HD/Съёмка/исходники"
python3 tools/env_paths.py set project_root "/Volumes/Macintosh HD/Съёмка/проект"
python3 tools/env_paths.py show
```

## 5. Запустить Resolve и проверить скриптовый API

```bash
python3 tools/start_resolve.py --wait 90
python3 skills/davinci-resolve-workbench/scripts/resolve_doctor.py
```

В самом Resolve включи внешний скриптовый API:
*Preferences → System → General → External scripting using local network*.

## 6. Модалка блокирует скрипты

```bash
python3 tools/dismiss_dialogs.py --dry-run
python3 tools/dismiss_dialogs.py
```

Закрытие окон на macOS идёт через AppleScript — для этого терминалу нужен
разрешённый доступ к «Системным событиям» (*Конфиденциальность → Автоматизация*).

## 7. Зависимости для DRX

```bash
cd vendor && npm install && cd ..
```

## Мелочи, которые экономят время

* Имена файлов — **без пробелов и кириллицы**: macOS различает регистр, а Finder
  нормализует Unicode, и линк в Resolve потом не найдёт файл.
* Внешний скриптовый API на macOS требует разрешения на «локальную сеть».
* `python3` в системе Apple — 3.9; для `faster-whisper` и OpenCV лучше 3.11+.
* Если `doctor` ругается на права записи в `/Library` — LUT копируются в
  `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT`
  (права администратора могут потребоваться один раз).
