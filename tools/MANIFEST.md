# MANIFEST — инструменты пакета ZOVod Video

Каталог всех переносимых инструментов. Одна строка на инструмент.

**Проверен** = `python -m py_compile` проходит И запуск с `--help` отрабатывает без
трассировки. **Не проверен** = перенесён, но на этой машине не запускался (нужны
исходники проекта, Resolve или сеть) — помечены явно.

Пути в примерах — от корня пакета (`<ПАКЕТ>`). Настройка путей среды —
`tools/env_paths.py`; проверка окружения — `python tools/doctor.py`.

---

## tools/ — ядро

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/env_paths.py` | Единая конфигурация путей: ffmpeg/ffprobe, Resolve, LUT, node, src_root; `set/show/unset` | `python tools/env_paths.py show` | stdlib | проверен |
| `tools/doctor.py` | Проверка окружения: python, ffmpeg, Resolve, LUT, node+вендор, диск, ключ SFXMint | `python tools/doctor.py --json` | stdlib | проверен |
| `tools/checkpoint.py` | Точки отката: снимок/список/восстановление рабочего дерева | `python tools/checkpoint.py save stage3 "описание"` | stdlib | проверен |
| `tools/new_project.py` | Скаффолд нового проекта по канону среды (раскладка, project.json, README, копия инструментов) | `python tools/new_project.py demo --src "D:\src" --fps 25` | stdlib | проверен |
| `tools/verify_timeline.py` | Структурная проверка таймлайна **внутри Resolve**: gaps/overlaps, длительность, карта треков; принимает `--job` с ожиданиями | `python tools/verify_timeline.py --job templates/verify_job.json` | Resolve API (для реальной проверки) | проверен (запуск из консоли; внутри Resolve — по среде монтажа) |
| `tools/resolve_probe_env.py` | Проба скриптового API Resolve (версия, таймлайн, рендер-джобы) — исполняется внутри Resolve | `exec(compile(open(r'<ПАКЕТ>/tools/resolve_probe_env.py').read(),'x','exec'))` | Resolve API | проверен (вне Resolve отдаёт JSON с ошибкой, без трассировки) |
| `tools/resolve_sandbox_audio.py` | Песочница: проверка поведения Resolve при добавлении аудио | как выше, через `run_script_unsafe` | Resolve API + тестовый WAV (`$ZOVOD_SANDBOX_WAV`) | проверен (вне Resolve — JSON-ошибка без трассировки) |
| `tools/resolve_sandbox_collide.py` | Песочница: поведение Resolve при коллизии длительностей | как выше | Resolve API + тестовый WAV | проверен (вне Resolve — JSON-ошибка без трассировки) |
| `tools/resolve_sandbox_drx.py` | Песочница: применение DRX-грейда средствами Resolve | как выше | Resolve API + папка с .drx (`$ZOVOD_SANDBOX_DRX`) | проверен (вне Resolve — JSON-ошибка без трассировки) |
| `tools/check_deliverables.py` | Приёмочная проверка выдачи: ссылки в документах, числа против scene_map.json, состав обработанных файлов, точки отката | `python tools/check_deliverables.py --out <проект> --docs "ХРОНОЛОГИЯ_СЦЕН.md"` | stdlib | проверен |
| `tools/project_db_check.py` | Проверка целостности Project.db Resolve (только чтение): integrity_check, таблицы, таймлайны | `python tools/project_db_check.py --project <имя>` | stdlib | проверен |

## tools/audio/ — звук

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/audio/process_audio.py` | Финальная обработка звука всех клипов: highpass 80 → RNNoise → нормализация речи к −16 LUFS + лимитер; отчёты до/после | `python tools/audio/process_audio.py --inventory inventory.json --scene-map scene_map.json` | ffmpeg, numpy, модель RNNoise | проверен (синтаксис/CLI; прогон требует исходников и модели) |
| `tools/audio/process_audio_new.py` | То же для выбранного списка клипов, с распознаванием «речь/атмосфера» по расшифровке и энергетике | `python tools/audio/process_audio_new.py --inventory inventory.json --clips "A,B"` | ffmpeg, numpy, faster-whisper (только если нужны транскрипты) | проверен (синтаксис/CLI; прогон требует исходников) |
| `tools/audio/measure_audio.py` | Замеры звука по всем клипам: peak, RMS, LUFS, клиппинг, DC offset, пол/ SNR, доля речи, паузы | `python tools/audio/measure_audio.py --inventory inventory.json` | ffmpeg, ffprobe, numpy | проверен (синтаксис/CLI; прогон требует инвентаризации) |
| `tools/audio/build_clip_cut.py` | Пересборка звука клипа из оригинала с вырезанием «дыр»; проверка по пословной расшифровке, усечение дыр со словами | `python tools/audio/build_clip_cut.py --src <исх> --jobs jobs.json` | ffmpeg, numpy, faster-whisper | проверен (синтаксис/CLI; прогон требует исходников и модели) |
| `tools/audio/verify_cut_files.py` | Независимая проверка пересобранных клипов: ffprobe, тишина, клиппинг, пословная сверка оригинал↔cut | `python tools/audio/verify_cut_files.py --src <исх> --plan audio/cut_plan.json` | ffmpeg, ffprobe, faster-whisper | проверен (синтаксис/CLI; прогон требует результата build_clip_cut) |
| `tools/audio/verify_energy.py` | Проверка, что пересборка не потеряла речь: корреляция огибающих и доля окон в пределах ±6 дБ | `python tools/audio/verify_energy.py --src <исх> --plan audio/cut_plan.json` | ffmpeg, numpy | проверен (синтаксис/CLI; прогон требует результата build_clip_cut) |

## tools/asr/ — распознавание речи

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/asr/transcribe.py` | Локальная транскрипция клипов через faster-whisper (JSON + TXT + сводный TRANSCRIPTS.md) | `python tools/asr/transcribe.py --src <исх> --model small` | ffmpeg, faster-whisper | проверен (синтаксис/CLI; прогон требует модели) |
| `tools/asr/transcribe_chunks.py` | Распознавание по кускам 15 с (обход `mkl_malloc` на длинных клипах), фильтр сегментов по logprob/no_speech | `python tools/asr/transcribe_chunks.py --clips "A,B" --src <исх>` | ffmpeg, numpy, faster-whisper | проверен (синтаксис/CLI; прогон требует модели) |
| `tools/asr/compare_text.py` | Текстовая сверка оригинала и пересобранного файла: какие слова должны прозвучать и прозвучали | `python tools/asr/compare_text.py --plan audio/cut_plan.json` | stdlib | проверен (синтаксис/CLI; прогон требует cut_plan.json) |
| `tools/asr/compare_words.py` | Пословная сверка по времени с картой cut→src: подтверждённые, потерянные, новые слова | `python tools/asr/compare_words.py --plan audio/cut_plan.json` | ffmpeg, numpy, faster-whisper | проверен (синтаксис/CLI; прогон требует cut_plan.json) |

## tools/inventory/ — инвентаризация и измерения

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/inventory/inventory_scan.py` | Инвентаризация исходников: ffprobe по каждому видео (длительность, разрешение, fps, кодеки, таймкод) | `python tools/inventory/inventory_scan.py --src <исх>` | ffprobe | проверен (синтаксис/CLI; прогон требует исходников) |
| `tools/inventory/measure_shake.py` | Тряска камеры по всем клипам: phase correlation, снятие дрейфа, RMS/p95 тряски в px и 4K, порог обрезки | `python tools/inventory/measure_shake.py --inventory inventory.json` | ffmpeg, numpy, opencv | проверен (синтаксис/CLI; прогон требует инвентаризации) |
| `tools/inventory/measure_pauses.py` | Провалы в звуке: цифровой ноль или тихая запись, уровень фона вне провалов | `python tools/inventory/measure_pauses.py --wav a.wav --pauses "18.8-20.7"` | ffmpeg, numpy | проверен (синтаксис/CLI; прогон требует звука) |
| `tools/inventory/measure_sfx.py` | Замеры звуковых эффектов той же методикой, что process_sfx.py | `python tools/inventory/measure_sfx.py a.wav b.wav` | ffmpeg, numpy | проверен (синтаксис/CLI; прогон требует звука) |
| `tools/inventory/extract_clip_frames.py` | Опорные кадры 960×540 (18 %, 50 %, 82 % длительности) для посцензорного баланса | `python tools/inventory/extract_clip_frames.py --src <исх>` | ffmpeg, ffprobe | проверен (синтаксис/CLI; прогон требует исходников) |

## tools/scene/ — карта сцен

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/scene/scene_map.py` | Хронологическая карта сцен: инвентаризация + транскрипции + замеры звука/тряски + ручная классификация → scene_map.json и ХРОНОЛОГИЯ_СЦЕН.md | `python tools/scene/scene_map.py --out <проект> --classification scene_classification.json` | stdlib | проверен (синтаксис/CLI; прогон требует наполненного проекта) |

Ручная классификация (`blocks` / `clips` / `speech_types` / `prompt_echo`) — это
проектные данные, они лежат во внешнем JSON, а не в коде.

## tools/color/ — цвет и грейд

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/color/make_luts.py` | Три направления грейда в .cube (33³), защита кожи по HUE, копирование в папку LUT Resolve | `python tools/color/make_luts.py --out <проект>` | numpy | проверен (синтаксис/CLI) |
| `tools/color/make_luts_v2.py` | Луки v2: 3 стиля × 5 регистров сцен, white ceiling | `python tools/color/make_luts_v2.py --out <проект>` | numpy | проверен (синтаксис/CLI) |
| `tools/color/grade_previews.py` | Сравнительный лист грейдов на реальных кадрах: 5 вариантов × N кадров + крупные стил-кадры | `python tools/color/grade_previews.py --src <исх> --frames "САЛОН|C0131.MP4|4.0"` | ffmpeg | проверен (синтаксис/CLI) |
| `tools/color/look_preview.py` | Превью регистров сцены: оригинал сверху, грейд снизу (полный кадр 1600×900) | `python tools/color/look_preview.py --src <исх> --shots "M1|car|исх|<CLIP>|13" --look-module look.py` | ffmpeg, numpy, opencv | проверен (синтаксис/CLI). **Зависимость `look.py` в пакет не входит** — проектный файл, указывается через `--look-module`; без него скрипт выдаёт понятное сообщение и код 2 |
| `tools/color/compose_main_sheet.py` | Контактный лист по миниатюрам с подписями клипа и начала речи | `python tools/color/compose_main_sheet.py --thumbs thumbs --transcripts tr.json` | Pillow | проверен (синтаксис/CLI) |
| `tools/color/compose_pass3_sheet.py` | Контактный лист по кадрам захода (сетка 4×N) | `python tools/color/compose_pass3_sheet.py --frames pass3_frames` | Pillow | проверен (синтаксис/CLI) |
| `tools/color/compose_pass4_sheet.py` | Контактный лист по клипам с подписями из расшифровки | `python tools/color/compose_pass4_sheet.py --frames pass4_frames --json pass4_transcripts.json` | Pillow | проверен (синтаксис/CLI) |
| `tools/color/compose_faces.py` | Лист зума на лицо; область лица ищется автоматически по тону кожи | `python tools/color/compose_faces.py --src variants --dst compare --moments m.json --variants v.json` | Pillow, numpy, opencv | проверен (синтаксис/CLI) |
| `tools/color/compose_compare.py` | Сравнительные листы: полный кадр + зум на лицо | `python tools/color/compose_compare.py --src variants --dst compare --moments m.json --variants v.json` | Pillow | проверен (синтаксис/CLI) |
| `tools/color/compose_v2.py` | Финальные листы: оригинал + стили (полный кадр) + зум на лицо | `python tools/color/compose_v2.py --old variants --new v2 --dst compare_v2 --moments m.json --variants v.json` | Pillow | проверен (синтаксис/CLI) |
| `tools/color/build_labeled_sheet.py` | Контактный лист с подписью имени клипа на каждом кадре (ffmpeg drawtext + tile) | `python tools/color/build_labeled_sheet.py --thumbs thumbs` | ffmpeg | проверен (синтаксис/CLI) |
| `tools/color/make_drx.js` | Генерация .drx оффлайн из спецификации (первичный грейд + power window + несколько нод) | `node tools/color/make_drx.js examples/drx_spec.example.json out.drx` | node, `vendor/` (fzstd, zstd-codec) | **проверен реально**: 2910 байт, 3 узла, 2 связи, exit 0 |
| `tools/color/drx_lab/gen_drx_test.js` | Смоук-тест кодека: три DRX (primary, primary+window, многоузловой) | `node tools/color/drx_lab/gen_drx_test.js <папка>` | node, `vendor/` | **проверен реально**: 3 файла (1584 / 1809 / 2111 байт), exit 0 |
| `tools/color/drx_lab/compare_frames.py` | Попиксельное сравнение контрольных кадров: RMS, max-diff, доля пикселей с diff>1 | `python tools/color/drx_lab/compare_frames.py --dir drx_lab/stills` | numpy, Pillow | проверен (синтаксис/CLI) |

## tools/sfx/ — звуковые эффекты и SFXMint

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `tools/sfx/process_sfx.py` | Обработка SFX под стандарт проекта (48 кГц/стерео/pcm_s24le), итерации до целевого true peak, замеры до/после | `python tools/sfx/process_sfx.py --src sfx/orig --out audio/sfx` | ffmpeg, ffprobe, numpy | проверен (синтаксис/CLI; прогон требует оригиналов SFX) |
| `tools/sfx/sfxmint_call.py` | Прямой вызов SFXMint MCP (Streamable HTTP) без ключа: tools / call / batch | `python tools/sfx/sfxmint_call.py tools` | сеть | проверен (синтаксис/CLI) |
| `tools/sfx/sfxmint_download.py` | Скачивание оригиналов звуков по манифесту + сверка sha256 | `python tools/sfx/sfxmint_download.py manifest.json --out sfx/orig` | сеть | проверен (синтаксис/CLI) |
| `tools/sfx/sfxmint_summarize.py` | Компактная сводка по результатам поиска SFXMint (+ машинная версия в JSON) | `python tools/sfx/sfxmint_summarize.py search.json --json summary.json` | stdlib | проверен (синтаксис/CLI) |

Ключ `SFXMINT_API_KEY` читается только из переменной окружения и никогда не печатается.

## skills/davinci-resolve-workbench/ — скилл Resolve

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `skills/davinci-resolve-workbench/SKILL.md` | Инструкция скилла: проверка среды, правка API, запуск Resolve, грейд, рендер, сдача | — | — | проверен (пути обобщены, врезка добавлена) |
| `skills/davinci-resolve-workbench/references/environment.md` | Карта окружения: Resolve, MCP-обвязка, тулчейн, база проекта | — | — | проверен |
| `skills/davinci-resolve-workbench/references/resolve-api-gotchas.md` | Грабли скриптового API Resolve 21.1.1: что падает и как обходить | — | — | проверен |
| `skills/davinci-resolve-workbench/references/video-workflows.md` | Рабочие сценарии: импорт, таймлайн, QC, рендер, сдача | — | — | проверен |
| `skills/davinci-resolve-workbench/references/color-look-development.md` | Разработка грейда: LUT, ноды, DRX, проверка «до/после» | — | — | проверен |
| `skills/davinci-resolve-workbench/scripts/resolve_bridge.py` | stdio-клиент к ResolveMCP.exe: тот же протокол, но таймаут в минуты | `python skills/davinci-resolve-workbench/scripts/resolve_bridge.py script job.py --timeout=600` | Resolve запущен | проверен (CLI; работа с Resolve — по среде монтажа) |
| `skills/davinci-resolve-workbench/scripts/resolve_doctor.py` | Диагностика: процесс Resolve, MCP-сервер, mcp.json, ffmpeg, LUT | `python skills/davinci-resolve-workbench/scripts/resolve_doctor.py` | stdlib | проверен |
| `skills/davinci-resolve-workbench/scripts/media_probe.py` | Разведка медиа: метаданные, палитра, число кадров, таймкод | `python skills/davinci-resolve-workbench/scripts/media_probe.py file.mp4` | ffmpeg, numpy | проверен |
| `skills/davinci-resolve-workbench/scripts/frame_qc.py` | QC кадров: контрольные кадры, метрики, проверка стабилизации | `python skills/davinci-resolve-workbench/scripts/frame_qc.py compare --src A --graded B` | ffmpeg, numpy, Pillow | проверен |
| `skills/davinci-resolve-workbench/scripts/_doctor_state.py` | Вспомогательный: плоская строка состояния Resolve для парсинга | (используется resolve_doctor) | Resolve API | проверен |

## vendor/ — вендорские кодеки (MIT)

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `vendor/README.md` | Что это, зачем, установка, вызов | — | — | проверен |
| `vendor/package.json` | Зависимости npm: fzstd, zstd-codec | `cd vendor && npm install` | node | проверен (установка прошла: 2 пакета) |
| `vendor/resolve-mcp-advanced/LICENSE` | MIT-лицензия исходного проекта | — | — | проверен |
| `vendor/resolve-mcp-advanced/README.md` | Документация исходного проекта (MIT) | — | — | проверен |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/drx-codec/` | Кодек .drx: генератор/парсер/мерджер, извлечение параметров | (через tools/color/make_drx.js) | node, fzstd, zstd-codec | проверен (сгенерирован .drx) |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/drp-format/` | Формат .drp: сборка/валидация/дифф проекта | — | node | **не проверен** (в поставку входит, но не запускался) |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/drt-format/` | Формат .drt: билдер/парсер/валидатор, скоринг возможностей | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/drx-parameters/` | Реестр и калибровка параметров грейда | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/conform-qc/` | QC соответствия: адаптеры, сравнение, оракулы, упаковка | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/fusion-codec/` | Кодек Fusion-композиций | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/fairlight/` | Кодек Fairlight | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/audio/` | Аудио: конвертер форматов, сплит, трим | — | node | **не проверен** |
| `vendor/resolve-mcp-advanced/resolve-advanced/vendor/audio-fairlight/` | Аудио Fairlight | — | node | **не проверен** |

## templates/ и examples/

| путь | что делает | пример команды | зависимости | проверен |
|---|---|---|---|---|
| `templates/verify_job.json` | ШАБЛОН ожиданий для `tools/verify_timeline.py` (те же ключи, значения очищены) | `cp templates/verify_job.json <проект>/verify_job.json` | — | проверен |
| `examples/drx_spec.example.json` | Пример спецификации для генерации .drx | `node tools/color/make_drx.js examples/drx_spec.example.json out.drx` | — | проверен (использован в проверке) |
| `examples/grade_spec.example.json` | Пример спецификации грейда | — | — | проверен |
| `examples/reports/*.example.json` | Примеры отчётов инструментов | — | — | проверен |
