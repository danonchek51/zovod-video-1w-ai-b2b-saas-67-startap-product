# Быстрый старт — Windows

Для машин на Windows. Полная версия — `docs/ENVIRONMENT.md`, различия платформ —
`PLATFORMS.md`.

## 1. Проверить, что всё на месте

```powershell
python tools\doctor.py
```

Если `python` не найден — поставь Python 3.12+ (`winget install Python.Python.3.12`)
и перезапусти терминал.

## 2. Поставить недостающее

```powershell
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
pip install numpy opencv-python pillow faster-whisper
```

DaVinci Resolve — обычная установка с сайта Blackmagic либо портативная сборка.

## 3. Указать свои пути

```powershell
python tools\env_paths.py set src_root    "F:\Съёмка\исходники"
python tools\env_paths.py set project_root "F:\Съёмка\проект"
python tools\env_paths.py show
```

Если Resolve портативный (папка с `Resolve.exe` внутри `Downloads` или `Tools`):

```powershell
python tools\env_paths.py set resolve_exe "<путь к Resolve.exe>"
```

## 4. Запустить Resolve и проверить скриптовый API

```powershell
python tools\start_resolve.py --wait 90
python skills\davinci-resolve-workbench\scripts\resolve_doctor.py
```

## 5. Модалка блокирует скрипты

```powershell
python tools\dismiss_dialogs.py --dry-run   # посмотреть
python tools\dismiss_dialogs.py             # закрыть и перезапустить
```

## 6. Зависимости для DRX

```powershell
cd vendor
npm install
cd ..
```

## Мелочи, которые экономят время

* Пути с пробелами и кириллицей работают, но в командах оборачивай в кавычки:
  `python tools\env_paths.py set src_root "F:\Съёмка\исходники"`.
* PowerShell 5.1 читает `.ps1` без BOM как ANSI — поэтому в пакете нет `.ps1`
  с кириллицей, а функциональность переехала в Python-скрипты.
* Имена файлов, которые уходят в Resolve, — **без пробелов и кириллицы**.
* Раз в папку добавлен `node_modules` — он в `.gitignore`, зависимости ставятся
  командой выше.
