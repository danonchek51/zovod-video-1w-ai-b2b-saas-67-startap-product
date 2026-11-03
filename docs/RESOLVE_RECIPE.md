# RESOLVE_RECIPE.md — что реально работает в Resolve 21.1.1 (проверено)

> Документ перенесён из рабочей среды монтажа и обобщён: названия проекта, клипов и людей заменены плейсхолдерами. Проверенные факты и числа сохранены.

**Проверено на:** DaVinci Resolve Studio **21.1.1.10** (портативная сборка), официальный MCP `davinci-resolve` (Aspect), Python 3.14.
**Дата проверки:** 31.10.2026. Всё ниже помечено как **[В]** — измерено и воспроизведено, **[Д]** — известная граница из документации/чужих отчётов.

> Правило среды: в этом документе живут только **проверенные** утверждения. Всё, что не проверено, помечено и не должно подаваться как факт.

---

## 1. Проект и менеджер проектов

| Вызов | Статус | Комментарий |
|---|---|---|
| `pm.LoadProject(name)` | **[В]** работает | `pm.OpenProject` **не существует** |
| `pm.CreateProject(name, mediaPath=None)` | **[В]** работает | удобно для одноразовых песочниц |
| `pm.CloseProject(proj)` / `pm.DeleteProject(name)` | **[В]** работают | DeleteProject требует, чтобы проект **не был загружен** — сначала CloseProject |
| `pm.SaveProject()` | **[В]** работает | сохраняет текущий проект под своим именем |
| `pm.GetProjectListInCurrentFolder()` | **[В]** работает | |
| `proj.GetMediaPool().CreateEmptyTimeline(name)` | **[В]** работает **только в реальном проекте** | ⚠️ В «Untitled Project» (проект не сохранён) возвращает **None** — медиапула нет. Все операции с таймлайнами — только в сохранённом проекте |

## 2. Таймлайн

| Вызов | Статус | Комментарий |
|---|---|---|
| `tl.AddTrack('audio', 'stereo')` | **[В]** работает | `trackIndex` — **1-based** (первая аудиодорожка = 1) |
| `tl.AddTrack('video')` | **[В]** работает | |
| `tl.SetTrackName(type, idx, name)` | **[В]** работает | |
| `tl.GetTrackSubType('audio', idx)` | **[В]** работает | вернул `'stereo'` |
| `tl.SetTrackEnable / SetTrackLock / GetIsTrackEnabled / GetIsTrackLocked` | **[В]** работают | |
| `tl.GetSetting('timelineFrameRate')` | **[В]** работает | **24.0 по умолчанию в новом проекте** — не хардкодить fps, читать из таймлайна |
| `tl.GetSettings()` | **[В]** работает | возвращает dict со всеми настройками |
| `tl.AddMarker(frame, color, name, note, duration, customData)` | **[В]** работает | `color` — строка из списка: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream. `customData` принял и **строку**, и **dict** |
| `tl.GetMarkers()` | **[В]** работает | ключ — int-кадр, значение — dict с color/duration/name/note/customData |
| `tl.DetectSceneCuts()` | **[В]** работает | только как **подсказка границ**, не как решение монтажа |
| `tl.NormalizeAudioLevel(items, opts)` | **[В]** метод есть | ⚠️ поведение на 21.1.1 отдельно не проверялось — сначала dry-run на копии |
| `tl.GetNormalizeAudioModes()` | **[В]** работает | **14 режимов**: Sample Peak Program, True Peak, ITU-R BS.1770-1, **ITU-R BS.1770-4**, **ATSC A/85**, **EBU R128**, OP-59, TR-B32, AGCOM 219/09/CSP, **Netflix**, **YouTube**, Disney 2.0, Disney 5.1+, TencentVideo |
| `tl.GetVoiceIsolationState(idx)` / `SetVoiceIsolationState` | **[В]** работают | Resolve 21 Voice Isolation |
| `tl.CreateSubtitlesFromAudio(autoCaptionSettings)` | **[В]** метод есть | для автосубтитров — но в нашем ролике титры шуточные, см. C0127 |
| `tl.DuplicateTimeline(name)` | **[В]** работает | рабочий способ «новая версия таймлайна перед правкой» |
| `tl.DeleteClips(items, ripple=False)` | **[Д]** | на таймлайновых клипах ранее возвращал False |
| `mp.DeleteTimeline(name)` | **[В] НЕ СУЩЕСТВУЕТ** | ⚠️ Удаление таймлайна через API недоступно: удалить проект (`pm.DeleteProject`) или вручную в UI |

## 3. Медиапул и расстановка

| Вызов | Статус | Комментарий |
|---|---|---|
| `mp.ImportMedia([path, ...])` | **[В]** работает | **только список строк**; со словарями возвращает пусто. Возвращает dict |
| `mp.AppendToTimeline([AppendClipInfo])` | **[В]** работает | ключ к успеху — кадровая расстановка звука |
| `AppendClipInfo.mediaType` | **[В]** | `2` = только аудио (проверено: видео не появилось) |
| `AppendClipInfo.trackIndex` | **[В]** | **1-based** для аудио |
| `AppendClipInfo.recordFrame` | **[В]** | **абсолютная позиция на таймлайне** — проверено: `recordFrame=100` → айтем `start=100, end=150` |
| `AppendClipInfo.startFrame/endFrame` | **[В]** | границы **исходника** (в кадрах), `endFrame-startFrame` = длина айтема |
| Поведение при повторной расстановке | **[В]** | `AppendToTimeline` **не риплит** — перекрытие не сдвигает соседей. Место под дорожку планировать заранее |
| **Коллизия: `recordFrame` внутрь существующего айтема** | **[В]** | **Не перезаписывает и не отбрасывает.** Новый айтем сдвигается на конец занятого участка и **обрезается по длине**: запросили `recordFrame=120`, 50 кадров, занято 100–150 → встал на **150–170** (20 кадров). Т.е. поведение — «встать в первое свободное место и укоротить», а не «collision rejection». **Следствие: звук может молча укоротиться — всегда сверять длину фактически размещённого айтема** |
| `mp.DeleteClips(items)` | **[В]** | на таймлайновом клипе ранее возвращал False |
| `proj.InsertAudioToCurrentTrackAtPlayhead(path, off, dur)` | **[Д]** | документировано как ненадёжное (зависит от трека/страницы/плейхеда). **Не использовать** — есть `AppendToTimeline` |
| `MediaPoolItem.GetName` / `TimelineItem.GetName` | **[В] грабли** | в этой связке это **строковое свойство, а не метод** — `item.GetName()` даст `TypeError: 'str' object is not callable`. Официальный API объявляет их методами — **проверять оба вида**: `v = getattr(it,'GetName',None); name = v() if callable(v) else v` |

**Рабочий рецепт расстановки звука (проверен):**
```python
items = mp.ImportMedia([wav_path])            # dict
res = mp.AppendToTimeline([{
    "mediaPoolItem": list(items.keys())[0],
    "startFrame": 0, "endFrame": frames_of_sound,
    "mediaType": 2,                            # только аудио
    "trackIndex": 1,                           # 1-based
    "recordFrame": event_frame,                # абсолютный кадр
}])
item = res[0]
assert item.GetStart() == event_frame
```

## 4. Громкость, панорама, тембр

`TimelineItem.GetProperties()` / `SetProperties(dict)` — **[В]** работают.

| Ключ | Диапазон | Статус |
|---|---|---|
| `AudioVolumeEnabled` / `AudioVolume` | −100…+30 dB | **[В]** запись и чтение подтверждены: 0.0 → −6.0 |
| `AudioPanEnabled` / `AudioPan` | −100…100 | **[В]** читается |
| `AudioPitchEnabled` / `AudioPitchSemiTones` / `AudioPitchCents` | −24…24 / −100…100 | **[В]** читается |
| `AudioVoiceIsolationEnabled` / `AudioVoiceIsolationAmount` | 0…100 | **[В]** читается (Active Timeline Only) |
| `AudioDialogueLevelerEnabled` / `…Mode` / `…ReduceLoudDialogue` / `…LiftSoftDialogue` / **`…BackgroundReduction`** / `…OutputGain` | 0…6 dB | **[В]** читается **и пишется**: `SetProperties({'AudioDialogueLevelerBackgroundReduction': True})` → True, readback `false → true` |

**Важно:** утверждение «`AudioVolume` ненадёжен на 21.1.1» — **не подтвердилось**. Оно пришло из теста чужого MCP-сервера и относилось к методу `SetProperty("Volume")` (строковому), а не к `SetProperties` с ключом `AudioVolume`. У нас запись работает и читается обратно. Одноключевой геттер `item.GetProperty("AudioVolume")` тоже работает.

**`AudioDialogueLeveler…BackgroundReduction`** — нативный авто-дакинг Resolve 21. Отчёты называют Dialogue Leveler «UI-only» — это верно про **отдельный метод** (`SetDialogueLeveler` в API нет), но **через `SetProperties` свойство записывается**. ⚠️ Проверено только чтение/запись свойства; **звуковой эффект (тише ли фон под речью) требует отдельной проверки прослушиванием/рендером.**

## 5. Цвет — где проходит граница

| Что | Статус | Комментарий |
|---|---|---|
| CDL на клипе (Slope/Offset/Power) | **[В]** работает | `item.SetCDL(...)` / `item.GetCDL` |
| LUT на клипе | **[В]** работает | `item.SetLUT(...)`; LUT только из папки Resolve + `RefreshLUTList()` после копирования |
| Создание нод через API (`AddNode`/`AddSerial`/`AddParallel`) | **[Д]** отсутствует в API | ноды не создаются напрямую — но их можно **принести файлом** (см. DRX ниже) |
| **`.drx` → `Graph.ApplyGradeFromDRX(path, 0)`** | **[В] РАБОТАЕТ на 21.1.1** | см. §5.1 — многоузловой цвет, окна и квалификаторы открыты |
| Fusion-комп и `ExportCurrentFrameAsStill` | **[В]** | рендерится **только цветовая ветка**; зерно/текстура видны лишь в рендер-джобе |
| Порядок CDL → LUT | **[В]** | RMS 0,0065 против 0,0294 для обратного порядка |
| Точность `ExportCurrentFrameAsStill` vs ffmpeg | **[В]** | RMS 1,26/255 (8-битная погрешность); `ResetAllGrades()` → RMS 0,000 |

### 5.1. DRX — рабочий путь к многоузловому цвету (проверено 31.10.2026)

**Источник кодека:** `vendor/resolve-mcp-advanced/resolve-advanced/vendor/drx-codec/`
(MIT, вендорнут в пакет). Зависимости `zstd-codec` и `fzstd` ставятся командой
`cd vendor && npm install` — тогда они оказываются в `<ПАКЕТ>/vendor/node_modules`,
и Node находит их вверх по дереву (вендорнутое дерево не менялось).

**Что подтверждено измерением в песочнице `AGENT_SANDBOX3` (Resolve 21.1.1.10):**

| Сгенерированный файл | `ApplyGradeFromDRX` | Что Resolve рапортует в графе |
|---|---|---|
| `drx_primary_r21.drx` ( CDL/primary) | **True**, без краша | 1 нода, label из файла, тулы: `Primary Balance`, `Saturation, Hue & Lum Mix`, `Log Grade` |
| `drx_window_r21.drx` (primary + power window) | **True**, без краша | 1 нода, тулы: `Primary Balance`, **`Power Windows`** |
| `drx_multinode_r21.drx` (2 ноды + связь) | **True**, без краша | **2 ноды**: `Node 1`, `Node 2` |

**Рабочий цикл:**
```python
# 1) сгенерировать (node): require(.../vendor/resolve-mcp-advanced/resolve-advanced/vendor/drx-codec/drx-generator.js)
xml = await generateDRX(gradeParams, {label, width, height, resolveVersion: '21'})
# 2) применить (в Resolve, на айтете таймлайна):
g = item.GetNodeGraph()
ok = g.ApplyGradeFromDRX(path, 0)          # 0 = без ключевых кадров
# 3) ДОКУМЕНТИРОВАТЬ ПРИМЕНЕНИЕ — этого не сделать нельзя:
n = g.GetNumNodes()
labels = [g.GetNodeLabel(i) for i in range(1, n+1)]
tools  = [g.GetToolsInNode(i) for i in range(1, n+1)]   # ← доказательство, что грейд приземлился
```

**Правила и грабли (измерено):**
- `ApplyGradeFromDRX` **возвращает True даже тогда, когда картинка не изменилась** — всегда сверять `GetToolsInNode` и рендер, а не только флаг.
- Генерировать с `resolveVersion: '21'`: кодек по нему выбирает ветку wire-формата для окон (`isResolve21()`), но **заголовок `DbAppVer` в файле остаётся `19.1.3.0007`** — Resolve 21.1.1 такой файл принимает (проверено), но при выявлении проблем первым делом стоит поправить заголовок.
- Формат файла: XML-обёртка `<Gallery::GyStill>` с `<Body>` — hex-строка, в ней бинарное тело `0x81` + ZSTD + protobuf.
- **Артефакт песочницы:** в одноразовом проекте `ExportCurrentFrameAsStill` отдаёт **полностью прозрачный (чёрный) кадр** — вьювер не декодирует медиа в свежесозданном проекте. В рабочем проекте экспорт живой (4K, p1 7.0, p99 245, клиппинг 0.86 %). **Вывод: визуальную проверку DRX делать в рабочем проекте, а в песочнице — только граф.**
- Читать граф: `GetNumNodes()` (не `GetNodeCount` — его нет), `GetNodeLabel(i)`, `GetToolsInNode(i)`.

**Что осталось непроверенным:** попиксельное соответствие DRX → картинка на **рабочем** проекте (нужен выбор стиля грейда), применение HSL-кривых/квалификаторов/Resolve FX через DRX (кодек это умеет, но на нашей версии не проверено), зерно (только через рендер-джоб).

## 6. Как запускать скрипты в Resolve

| Правило | Почему |
|---|---|
| Скрипт — файл UTF-8, запуск через `exec(compile(open(path, encoding='utf-8').read(), name, 'exec'))` | транспорт MCP ломает кириллицу в inline-коде |
| `run_script` (песочница) — только работа с API Resolve | `import os`, файловая и сетевая работа заблокированы |
| `run_script_unsafe` — файловая/сетевая/процессная работа | вызывать с обоснованием, проговаривать заказчику |
| PowerShell 5.1 читает `.ps1` без BOM как ANSI | **кириллицу в `.ps1` не использовать** (ASCII-only) |
| 4K PNG из скрипта читать как `open(path,'rb')` + `io.BytesIO` | на существующих файлах были спорадические `FileNotFoundError` |

**macOS:** PowerShell-замены — `ls`, `grep`, `cat`, `cp`, `rm`; правило «ASCII-only в `.ps1`» переносится на `.sh` (то же без BOM и без кириллицы в самом скрипте).

## 7. Песочница для проверки возможностей

Для проверки API **без риска для пользовательских проектов**:
```python
pm = resolve.GetProjectManager()
p = pm.CreateProject("AGENT_SANDBOX")          # или pm.LoadProject, если уже есть
... проверки ...
pm.CloseProject(p); pm.DeleteProject("AGENT_SANDBOX")
```
⚠️ В песочнице таймлайн создаётся, но **`mp.DeleteTimeline` не существует** — таймлайн удаляется только вместе с проектом.

Готовая проверка аудио-пути: `python tools/resolve_sandbox_audio.py` (создаёт/удаляет песочницу сам).
Пробник окружения без мутаций: `python tools/resolve_probe_env.py`.

## 8. Таймкод и fps текущего проекта

- Проверено на тестовой сборке: таймлайн `Grade_Test` — 38 клипов, **16 908 кадров = 676,32 с** при 25 fps, старт **кадр 90000** (= 01:00:00:00 при 25 fps).
- Проверка: `python tools/verify_timeline.py` — длительность, дыры, наложения, нулевые айтемы, маркеры, ожидания из `templates/verify_job.json`.

## 9. Реальная поверхность API этого биндинга

Стаб `DaVinciResolveScript.pyi` **неполон** (в нём нет `GetSetting`, `GetNumNodes`, `GetToolsInNode`). Реальный список получен через `dir()` — проверенные имена:

- **`resolve`**: `GetProjectManager`, `GetCurrentProject`, `GetCurrentTimeline`, `GetMediaPool`, `GetGallery`, `GetVersionString`, `IsStudio`, `OpenPage`, `GetCurrentPage`, `GetFairlightPresets`, `GetRenderPresetList`… — **`ExportCurrentFrameAsStill` здесь НЕТ**.
- **`project`**: `ExportCurrentFrameAsStill(filePath)`, `GetSetting`, `SetSetting`, `GetSettings`, `SetSettings`, `SetCurrentTimeline`, `GetTimelineByIndex` (**по индексу, не по имени**), `GetTimelineCount`, `GetMediaPool`, `RefreshLUTList`, `AddRenderJob`, `StartRendering`, `GetRenderJobStatus`, `SetRenderSettings`, `GetRenderFormats/Codecs/Resolutions`, `LoadRenderPreset`, `ApplyFairlightPresetToCurrentTimeline`, `InsertAudioToCurrentTrackAtPlayhead`, `CreateSubtitlesFromAudio` (устаревшие `GetTranscribeAudioStatus`).
- **`timeline`**: `GetName`, `GetSetting`, `GetSettings`, `GetStartFrame`, `GetEndFrame`, `GetStartTimecode`, `SetStartTimecode`, `GetCurrentTimecode`, `SetCurrentTimecode`, `GetCurrentVideoItem`, `GetItemListInTrack`, `GetItemsInTrack`, `GetTrackCount`, `AddTrack`, `SetTrackName`, `SetTrackEnable/Lock`, `DeleteTrack`, `GetTrackSubType`, `AddMarker`, `GetMarkers`, `DeleteMarkerAtFrame`, `UpdateMarkerCustomData`, `GetMarkerCustomData`, `NormalizeAudioLevel`, `GetNormalizeAudioModes`, `GetVoiceIsolationState`, `SetVoiceIsolationState`, `DetectSceneCuts`, `DuplicateTimeline`, `DeleteClips`, `SetClipsLinked`, `CreateCompoundClip`, `CreateFusionClip`, `CreateSubtitlesFromAudio`, `Export`, `GrabStill`, `GetCurrentClipThumbnailImage`, `GetMarkInOut`, `SetMarkInOut`, `ConvertTimelineToStereo`, `GetNodeGraph`.
- **`timelineItem`**: `GetStart`, `GetEnd`, `GetDuration`, `GetName`, `GetNodeGraph`, `GetNumNodes`, `GetNodeLabel`, `GetLUT`, `SetLUT`, `SetCDL`, `GetCDL`, `ExportLUT`, `GetProperties`, `SetProperties`, `GetProperty`, `SetProperty`, `GetSpeed`, `SetSpeed`, `GetFades`, `SetFades`, `AddFusionComp`, `ImportFusionComp`, `GetFusionCompNames`, `DeleteFusionCompByName`, `GetLinkedItems`, `SetClipsLinked`, `GetSourceStartFrame/EndFrame`, `GetTrackTypeAndIndex`, `GetVoiceIsolationState`, `SetVoiceIsolationState`, `CopyGrades`, `ResetAllNodeColors`, `AddVersion`, `GetVersionNames`, `AddTake`, `GetTakesCount`.
- **`graph`**: `ApplyGradeFromDRX(path, gradeMode, applyToAllLayers)`, `GetNumNodes`, `GetNodeLabel`, `GetToolsInNode`, `SetNodeEnabled`, `GetLUT`, `SetLUT`, `ApplyArriCdlLut`, `ResetAllGrades`, `GetNodeCacheMode`, `SetNodeCacheMode`.

**Правило:** метод может отсутствовать в стабе, но существовать в рантайме, и наоборот — **неизвестный атрибут в этом биндинге возвращает `None`, а не бросает исключение** (отсюда `TypeError: 'NoneType' object is not callable` вместо понятного сообщения). Поэтому вызовы оборачивать так:

```python
def call(obj, name, *args):
    v = getattr(obj, name, None)
    if v is None:
        return None
    return v(*args) if callable(v) else v
```

**Проверка поверхности (read-only):**
```python
def pub(o): return sorted(n for n in dir(o) if not n.startswith('_'))
print(pub(resolve), pub(project), pub(timeline), pub(item), pub(graph))
```


---

## 10. Грабли при сборке медиапула (проверено 31.10.2026 на тестовой сборке)

| Грабля | Симптом | Решение |
|---|---|---|
| mp.ImportMedia([{...}]) | возвращает **пусто**, без ошибки | принимает **список строк**: mp.ImportMedia([path1, path2]); возвращает dict -> list(res.keys()) |
| Импорт без SetCurrentFolder | всё падает в корень медиапула | сначала mp.SetCurrentFolder(bin), потом ImportMedia |
| project.GetTimelineByIndex(i) | **None** при GetTimelineCount() == 1 | брать из медиапула: mediaPool.GetRootFolder().GetClipList()[i].GetTimeline() |
| timeline.GetItemCountInTrack / GetItemInTrack | **отсутствуют** в реальном биндинге | есть GetItemListInTrack(trackType, idx) -> список и DeleteClips([items]) |
| timeline.DeleteTimelineItem | отсутствует | timeline.DeleteClips([item]) |
| timelineItem.GetName | здесь **метод**, а на MediaPoolItem — **свойство** | `v = getattr(x,'GetName',None); v() if callable(v) else v` |
| timelineItem.GetProperty() | отдаёт только трансформ (Pan/Tilt/Crop) | свойства медиа -- в MediaPoolItem.GetClipProperty() |
| project.SetSetting('timelineFrameRate', 25) | **False** | значение ставится **строкой**: SetSetting('timelineFrameRate','25') -> True, читается как 25.0 |
| project.SetSetting('timelinePlaybackFrameRate','25') | False | остаётся 24 — так же в рабочем проекте, не мешает монтажу |
| project.SetSetting('timelineStartingTimecode','01:00:00:00') | False | ключа нет на уровне проекта; таймкод ставится на таймлайне: timeline.SetStartTimecode('01:00:00:00') |
| project.SetSetting('projectMediaLocation', path) | True | путь, куда Resolve кладёт прокси/рендеры |

**Рабочая последовательность для нового проекта:**

```python
pm = resolve.GetProjectManager()
p = pm.CreateProject('Name') or pm.LoadProject('Name')
p.SetSetting('timelineResolutionWidth', '3840')
p.SetSetting('timelineResolutionHeight', '2160')
p.SetSetting('timelineFrameRate', '25')          # строка!
p.SetSetting('videoMonitorFormat', 'HD 1080p 25')
mp = p.GetMediaPool()
root = mp.GetRootFolder()
bin = mp.AddSubFolder(root, 'BLOCK 1')
mp.SetCurrentFolder(bin)
items = list(mp.ImportMedia([path1, path2]).keys())
tl = mp.CreateEmptyTimeline('NAME')
tl.SetStartTimecode('01:00:00:00')
tl.AddTrack('audio', 'stereo')
pm.SaveProject()
```

---

## 11. Грабли медиапула и точка отката проекта (31.10.2026, проверено на тестовой сборке)

| Грабля | Симптом | Решение |
|---|---|---|
| `MediaPoolFolder.GetClipCount()` | **возвращает `None`** (метода нет в биндинге) -> `TypeError: 'NoneType' object is not callable` | считать через `len(folder.GetClipList())` |
| `MediaPoolFolder.GetSubFolderCount()` | то же самое | `folder.GetSubFolderList()` -> список бинов |
| `TimelineItem.GetTrackIndex()` | отсутствует | тип/индекс дорожки брать из `GetItemListInTrack(type, idx)` |
| `project.GetPath()` | отсутствует | путь к проекту в этом биндинге недоступен; использовать `pm.ExportProject` для бэкапа |
| `project.ExportCurrentFrameAsStill` — нет, есть `project.ExportCurrentFrameAsStill` | путать `resolve.ExportCurrentFrameAsStill` и `project.ExportCurrentFrameAsStill` | звать у `project` |

**Точка отката проекта Resolve** — экспорт `.drp`:

```python
pm.SaveProject()
pm.ExportProject("<ПРОЕКТ>", r"<ПАПКА_ЭКСПОРТА>\<ПРОЕКТ>_preclean.drp", False)
# -> True, файл ~0,16 МБ (медиа не встраивается, ссылки остаются)
```

`pm.ArchiveProject(projectName, filePath, isArchiveSrcMedia=True, isArchiveRenderCache=True, isArchiveProxyMedia=False)` — полный архив вместе с исходниками; для отката таймлайна хватает `ExportProject`.

**Песочница MCP `run_script`:** файловые и процессные импорты запрещены — `import os` даёт
`PermissionError: import not allowed: os`. Проверки по файлам делать в `run_script_unsafe`,
а в `run_script` — только API Resolve. Сам Resolve при этом пишет файлы штатно
(`ExportProject`, `ExportCurrentFrameAsStill` внутри скрипта работают).

**Отладка таймлайна без `GetItemCountInTrack`:** считать через
`len(tl.GetItemListInTrack("video", 1))` для каждой дорожки; тип дорожки — строка
`"video"` / `"audio"`, индекс с 1.

---

## 12. Импорт медиа: `ImportMedia` не работает, `MediaStorage` — работает (01.11.2026)

Проверено на портативной сборке Resolve 21.1.1 (тестовая сборка).

| Вызов | Симптом | Решение |
|---|---|---|
| `mp.ImportMedia([{"FilePath": p}])` | возвращает `None`, **в пул ничего не попадает** — ни на пути с кириллицей, ни на локальном ASCII-пути, ни WAV, ни MP3 | **не использовать** |
| `mp.ImportMedia([p])` (список строк) | раньше работало (31.10), **теперь тоже пусто** | — |
| `mp.ImportMedia(...)` на **24-бит WAV** | Resolve уходит в **100 % CPU и перестаёт отвечать на API** на 10+ минут (процесс жив, `Responding: False`, диалога нет) | если завис — сохранить проект заранее (`pm.SaveProject()` + `pm.ExportProject`), перезапустить Resolve, загрузить проект заново: монтаж и медиапул восстанавливаются без потерь |
| **`resolve.GetMediaStorage().AddItemListToMediaPool([{"media": path}])`** | **работает** — возвращает список `MediaPoolItem` | ✅ рабочий путь импорта |
| `ms.RevealInStorage(folderPath)` | раскрывает папку в Media Storage | делать перед импортом, иначе путь «не виден» |
| `mp.SetCurrentFolder(bin)` | куда попадут импортированные клипы | **обязательно** до импорта, иначе всё в текущую папку |
| `mp.AddSubFolder(root, name)` | создаёт бин | имя с кириллицей — ок, но **передавать через `\uXXXX`-escape**: inline-скрипт в MCP приходит в неверной кодировке и кириллица в нём искажается (проверка `"авар" in name` не срабатывала) |
| `mp.MoveClips(clips, folder)` / `mp.DeleteClips(clips)` | работают | удалить ошибочно импортированный клип из чужого бина |
| `mp.GetMarkers()` | в 21.1.1 возвращает **dict** `кадр → {name, note, color, duration, customData}` | `list(mk)` даст только кадры — имена потеряются |

**Рабочий рецепт импорта:**

```python
ms = resolve.GetMediaStorage()
ms.RevealInStorage(r"<ПАПКА_МУКСА>")
mp.SetCurrentFolder(bin)                     # куда класть
items = ms.AddItemListToMediaPool([{"media": r"<ПАПКА_МУКСА>\C0164.MP4"}])
```

**Кириллица в путях.** Скрипт, переданный через MCP `run_script`, доходит до
Resolve в неверной кодировке — кириллические литералы портятся. Рабочий
способ — передать путь как escape-строку (`"D:\\п"`) или вообще держать
в скрипте **файл** на диске и выполнять его через
`exec(compile(open(path, encoding='utf-8').read(), 'x.py', 'exec'), g)` — тогда
кириллица читается как UTF-8 и работает.

**Порядок в файле-скрипте:** `run_script_unsafe` с кастомным globals-dict
**теряет инъект `resolve`** — использовать `g = globals(); g['DRYRUN'] = True;
exec(compile(open(...).read(), 'x.py', 'exec'), g)`.



## 13. Импорт блока и работа с медиапулом (01.11.2026, 29 клипов)

Проверено на тестовой сборке, блок «БЛОК 11 · НОВОЕ (01.11.2026)».

### 13.1. Sandbox `run_script` не умеет файловые скрипты

В sandbox `run_script` **нет** `exec`, `globals`, `os` и любого `import` —
вызов падает с `NameError: name 'exec' is not callable` / `PermissionError:
import not allowed`. Скрипты, которые читают файлы (свой `.py` с диска) или
пишут отчёты, выполняются только через **`run_script_unsafe`**:

```python
g = globals()
exec(compile(open(r'<ПАПКА_СКРИПТОВ>\resolve_add_new_clips.py', encoding='utf-8').read(),
             'x.py', 'exec'), g)
result = g.get('report')
```

`g = globals()` обязателен: с кастомным globals-dict теряется инъект `resolve`.

### 13.2. `AppendToTimeline` тянет линкованный звук сам

Достаточно `{"mediaPoolItem": item, "recordFrame": кадр, "trackIndex": 1}` —
Resolve сам кладёт **видео на V1 и звук на первую свободную аудиодорожку (A1)
линком**. Отдельный вызов для звука не нужен (проверено на 29 айтемах:
длительности V1 и A1 совпали до кадра).

Нюансы:
- `recordFrame` = **конец таймлайна** (`tl.GetEndFrame()`), иначе клип
  встанет с перекрытием и Resolve **сдвинет и обрежет** монтаж;
- клипы ставятся подряд: `frame = it.GetEnd()` от предыдущего;
- клип 30 fps на таймлайне 25 fps пересчитывается по времени: округление
  кадров даёт до −1 кадра на клип (на 11 клипах суммарно −5).

### 13.3. `MediaPoolItem.ReplaceClip(path)` — замена файла без пересборки монтажа

Рабочий способ перелить исправленное медиа, **не трогая таймлайн**:

```python
it.ReplaceClip(r"<ПАПКА_МУКСА>\fixed\IMG_5473.MP4")   # -> True
```

- таймлайн обновляется сам (айтем ссылается на `MediaPoolItem`), позиции и
  длительности **не меняются**;
- `GetClipProperty("File Path")` показывает новый путь;
- применяется, когда файл на диске заменён (обрезка, перекодировка, починка).

### 13.4. Фактическая поверхность API: `GetClipProperty`, а не `GetProperty`

В стабе (`DaVinciResolveScript.pyi`) у `MediaPoolItem` заявлен `GetProperty`,
но **в рантайме этого биндинга такого метода нет** — обращение к нему даёт
`None`, и вызов `it.GetProperty(k)` падает с
`TypeError: 'NoneType' object is not callable`. Рабочий метод —
**`GetClipProperty(name)`** (плюс `SetClipProperty`, `GetMarkInOut`,
`ReplaceClip`, `ReplaceClipPreserveSubClip`).

Общее правило: **перед вызовом проверять `dir(obj)`** — неизвестный метод в
этом биндинге возвращает `None`, а не бросает исключение (см. §9).

### 13.5. Импорт пачкой

`MediaStorage.AddItemListToMediaPool([{"media": p}, ...])` — 28 файлов за один
вызов, ~2 мин, без зависания Resolve. Обязательно:
1. `mp.SetCurrentFolder(folder)` — **до** импорта, иначе файлы попадут не туда;
2. `ms.RevealInStorage(MUX_DIR)` — чтобы Resolve «увидел» папку;
3. имена файлов в муксе **с тем же расширением**, что на диске
   (`.MP4`, а не `.MOV`) — иначе `os.path.exists` вернёт False и файл
   молча не импортируется.

### 13.6. Скрипт расстановки должен быть идемпотентным

Тестовый прогон уже ставит первый клип (C0164) — полный прогон обязан его
пропустить, иначе будет дубль. Рабочая схема: собрать айтемы V1 с
`start >= BLOCK_START`, получить их имена через
`it.GetMediaPoolItem().GetName()` (`it.GetName()` на видео-айтеме **падает**),
пропустить уже стоящие и продолжить с конца последнего.

### 13.7. Выгрузка проекта

`pm.ExportProject(proj.GetName(), r"<ПАПКА_ЭКСПОРТА>\X.drp")` — работает,
файл ~0,2 МБ, **медиа не встраивается** (остаются ссылки на диск).

---

## 14. Пересборка фрагмента внутри таймлайна: замена источника + рипл (01.11.2026)

Задача: в середине готового монтажа заменить клип на пересобранный (вырезанные
паузы, новый звук) и **сдвинуть хвост монтажа**, не ломая синхронизацию звука
на других дорожках. Проверено на тестовой сборке, таймлайн `СБОРКА`.

### 14.1. Что умеет и что не умеет

| Приём | Поведение |
|---|---|
| `MediaPoolItem.ReplaceClip(path)` | меняет файл у существующего медиапул-айтема; позиции на таймлайне **не меняются** — годится, если длина совпадает |
| `AppendToTimeline` с `AppendClipInfo` (`mediaPoolItem`/`startFrame`/`endFrame`/`trackIndex`/`recordFrame`) | кладёт клип **точно** в заданные кадры; `endFrame` — **исключительно**; линкованный звук создаётся автоматически на `A1` |
| `Timeline.DeleteClips(items, rippleDelete=True)` | сдвигает последующие клипы **и маркеры**, но **только на дорожках удаляемого клипа** (V1/A1). Дорожки A2–A4 **не сдвигаются** |

### 14.2. Рабочая последовательность (4 шага)

1. **Снять** всё, что лежит на других дорожках в зоне правки (например, звук
   удара на A4) — иначе рипл его не сдвинет и он останется на старой картинке.
2. **Удалить** старые айтемы **без** рипла (`rippleDelete=False`).
3. **Поставить** новые айтемы через `AppendToTimeline` с точными
   source-диапазонами (`startFrame`/`endFrame` исходника) и `recordFrame`.
4. **Временно** занять освободившиеся кадры заглушкой, затем
   `DeleteClips([заглушка], rippleDelete=True)` — хвост монтажа и маркеры
   сдвинутся на нужное число кадров.

Возврат звука с A4 делается **вручную**: удалить старый айтим и вставить его
заново на новый кадр (свойства и фейды переносятся при переносе).

### 14.3. Грабли

- `AppendToTimeline` **не риплит**: без `recordFrame` клип ляжет в начало.
- При коллизии `AppendToTimeline` **сдвигает и обрезает** монтаж, а не
  перезаписывает — всегда сверять длину размещённого айтема.
- Дублирующий `append` с `mediaType: 2` в ту же позицию **не срабатывает**.
- `GetItemListInTrack("V1", 1)` → `None`; правильно — `GetItemListInTrack("video", 1)`
  и `GetItemListInTrack("audio", i)`.
- `tl.GetMarkers()` возвращает dict, `m.GetFrame()` **не работает** — читать `m["name"]`,
  кадр — из ключа.
- `project.GetMediaPoolItem()` в рантайме возвращает `None`; работает
  `project.GetMediaPool()`.
- `CreateEmptyTimeline` возвращает `None`, если имя занято — давать временным
  таймлайнам уникальные имена и **удалять их** после пробы.
- `run_script_unsafe` таймаутится на 10 с — задавать `timeout` 30–180 с;
  циклы по кадрам делать через ffmpeg в Python, а не в Resolve.
- **Перед финальной фиксацией перечитать таймлайн заново**: заказчик может
  параллельно править монтаж в том же проекте.

### 14.4. Переходы (Cross Fade) — не наложения

Resolve кладёт кросс-фейд на таймлайн **отдельным объектом**, который
закономерно перекрывает соседние клипы. Если считать по интервалам «как есть»,
нормальный монтаж с переходом выглядит как «наложения».

Признак перехода: `item.GetType()` → `"transition"`,
`item.GetMediaPoolItem()` → `None`, имя вроде `Cross Fade 0 dB`.

`python tools/verify_timeline.py` (исправлено 01.11.2026) определяет такие объекты
через `GetType()` с запасным признаком и **выносит их в отдельную категорию**
(`transitions` / `transition_spans`): в подсчёте дыр и наложений они не
участвуют, но видны в отчёте. Настоящие наложения (два обычных клипа поверх
другого) по-прежнему ловятся.

---

## 15. Крах Resolve: диагностика и восстановление (проверено 01.11.2026)

### 15.1. Как выглядит

Диалог «Отчет о проблемах DaVinci Resolve» блокирует скриптовый API: процесс
жив, но **MCP-вызовы виснут до таймаута** (`get_resolve_status` — 120 с и
ничего). Это не «Resolve не запущен», это «Resolve занят модальным окном».

### 15.2. Где смотреть причину

| файл | что в нём |
|---|---|
| `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\logs\ResolveDebug.txt` | подробный лог; в конце — `==========[CRASH DUMP]==========` |
| `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\logs\davinci_resolve.log` | краткий лог |
| `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\crash_archive.txt` | время краша, аптайм, версия |
| `%APPDATA%\...\Support\logs\*.dmp` | дамп |

**Важно:** при перезапуске Resolve логи **перезаписываются** — читать их надо
сразу, не откладывая.

Причина читается по последней строке `ERROR` перед `CRASH DUMP`. В нашем
случае:

```
DVIP | ERROR | DNN Model Blob e4a498a3bffcf745ca6cc136ec5a6635.bin not found
DVIP | ERROR | Failed to find O!B88E5F929076682B98895A8F964A63049CCF5… in e4a498a3….bin
==========[CRASH DUMP]==========
```

`DVIP` — нейросетевой движок Resolve. Файл `plugins\e4a498a3….bin` в сборке
**есть** (224 МБ, валидный заголовок), но запрошенного ключа модели в нём
нет → **дефект упаковки портативной сборки 7997**, не наши правки.

### 15.3. Порядок восстановления (без потери данных)

1. **Не нажимать «Отправить»** — отчёт о краше уйдёт на сервер Blackmagic.
2. Проверить живучесть проекта: `Project.db` лежит в
   `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Resolve Project Library\Resolve Projects\Users\guest\Projects\<Проект>\Project.db`.
   `sqlite3` → `PRAGMA integrity_check` → `ok` значит база цела (скрипт
   `project_db_check.py`).
3. Снять процесс Resolve и запустить заново:
   `python tools/dismiss_dialogs.py` (сам делает kill + relaunch; на macOS —
   через AppleScript System Events).
   **Кнопки краш-диалога нажать нельзя** — Resolve на Qt, Win32 их не видит.
4. Открыть проект (`pm.LoadProject('<ПРОЕКТ>')`) и **перечитать таймлайн**:
   диапазон, число айтемов, маркеры, наличие всех медиа на диске.
5. Перевыгрузить `.drp` (страховка) и снять точку отката.

### 15.4. Проверка «ничего не потерялось»

Сверяем с тем, что было до краша: диапазон таймлайна, число маркеров,
позиции ключевых клипов, `os.path.exists` по каждому `File Path` из
медиапула. На нашем крше совпало всё: 90000–102889 = 515,56 с, 18 маркеров,
`CLIP_A_cut.mp4` на 90309–91625, 66/66 медиа-ссылок живы.

### 15.5. Грабли

- **Логи перезаписываются** при перезапуске — снимать сразу.
- MCP-таймаут 120 с при живом Resolve = **модальное окно**, а не «Resolve упал».
  Проверять процесс (`Get-Process Resolve`) и заголовок окна.
  macOS: `Get-Process Resolve` → `ps aux | grep Resolve`.
- `project.GetProjectManager()` **не существует** — менеджер лежит на
  `resolve.GetProjectManager()`; на `project` такого метода нет, и вызов
  вернёт `None`, а `None.SaveProject()` даст
  `TypeError: 'NoneType' object is not callable`.
- В `run_script_unsafe` переменная `out`, объявленная проверочным скриптом,
  **затирает** ваш отчёт (скрипт исполняется в общий `globals()`) — называйте
  свои переменные иначе или забирайте результат под другим именем.
- PowerShell 5.1 читает `.ps1` без BOM как ANSI: **кириллица в `.ps1` ломает
  парсер**. Русские строки для сопоставления собирайте из кодов символов.
- Кириллица в выводе PowerShell → кракозябры в консоли; читать JSON-отчёты
  через Python (`print(json.dumps(..., ensure_ascii=False))` + `PYTHONIOENCODING=utf-8`).

---

## 16. Замена клипа: видео на V1, звук отдельным файлом на A1 + ripple

Проверенная последовательность (02.11.2026, клипы CLIP_B/CLIP_C таймлайна
«СБОРКА»):

1. **Прочитать текущее состояние** таймлайна (заказчик правит монтаж
   параллельно): позиции и `src` искомых айтемов искать по
   `GetMediaPoolItem().GetClipProperty("File Path")`, а не по жёстким
   константам — скрипт сам вычисляет новые координаты от найденного.
2. **Страховочный `.drp` до мутации**:
   `resolve.GetProjectManager().ExportProject(project.GetName(), drp_path)`.
3. **Удалить** старые айтемы клипа на V1 и A1: `tl.DeleteClips(items, False)`.
4. **Перелинковать** медиапул: `mp_item.ReplaceClip(new_file)` — медиапул
   переиспользует тот же элемент, бины не плодятся.
5. **Поставить видео**: `AppendToTimeline` с `mediaType="video"`,
   `trackIndex=1`, `recordFrame` = прежнее начало клипа на V1.
6. **Поставить звук отдельным файлом**: `ImportMedia("<path>.wav")` (строка!)
   → `AppendToTimeline` с `mediaType="audio"`, `trackIndex=1`,
   `recordFrame` = начало клипа на V1 **+ сдвиг синхронизации**.
   Сдвиг = разница in-point'ов видео и звука (напр. 405−190 = 215 кадров):
   тогда концы V1 и A1 совпадают и звук синхронен картинке.
   (`mediaType="audio"` для клипа с видео **игнорируется** — см.
   `docs/FAILURE_MODES.md` §23.)
7. **Сокращение хвоста**: «заглушка» из любого клипа на V1 длиной
   (старый конец − новый конец) в зоне, где должен быть хвост, затем
   `tl.DeleteClips([placeholder], True)` — ripple сдвигает хвост V1 и маркеры
   влево. Проверять фактом: длина дыры до/после должна совпасть.
8. **Маркеры внутри укороченного клипа** переносить **по содержимому**
   (число вырезанных кадров до маркера), а не простым сдвигом хвоста;
   `AddMarker(frameId, color, name, note, duration)` — порядок аргументов
   важен (см. `docs/FAILURE_MODES.md` §22).
9. **Проверка**: `python tools/verify_timeline.py` (наложения, дыры в зоне правки,
   длительность) + `python tools/check_deliverables.py`; затем `SaveProject` +
   `ExportProject` финального `.drp`.

**Отдельно:** `DeleteClips(..., rippleDelete=True)` сдвигает клипы и маркеры
**только на дорожке удаляемого клипа** — звук на A2–A4 и маркеры «внутри»
клипа остаются на месте, их надо переносить вручную.
