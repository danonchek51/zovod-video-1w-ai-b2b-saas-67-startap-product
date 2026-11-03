# vendor/ — вендорные кодеки DRX/DRP

## Что это

Офлайн-генераторы файлов грейда DaVinci Resolve (`.drx`) и проектов (`.drp`)
на **JavaScript**, без запущенного Resolve.

Источник: проект [`samuelgursky/davinci-resolve-mcp`](https://github.com/samuelgursky/davinci-resolve-mcp),
подкаталог `resolve-advanced/vendor/`. Лицензия — **MIT**, полный текст в
`vendor/resolve-mcp-advanced/LICENSE`, авторство сохранено.

Взят только кодек-слой (`vendor/resolve-mcp-advanced/resolve-advanced/vendor/`):
девять подпапок — `drx-codec`, `drp-format`, `drt-format`, `drx-parameters`,
`conform-qc`, `fusion-codec`, `fairlight`, `audio`, `audio-fairlight`.
Тесты (`__tests__`) оставлены: они подтверждают работоспособность кодека.

Не перенесено из исходного проекта (намеренно): `.git`, `install.py`,
`CHANGELOG.md` (1 МБ), `package-lock.json`, `server/`.

## Зачем

Позволяет собрать грейд (primary + power window + несколько нод) в файл `.drx`
**оффлайн** и затем применить его в Resolve через
`Graph.ApplyGradeFromDRX(path, 0)`. Без этого пришлось бы строить ноды
через API — а `AddNode` в скриптовом API Resolve 21.1.1 отсутствует.

Грейд-файл можно применить и без работающего Resolve: открыть `.drx` в
любом редакторе XML/DAX, отредактировать вручную и положить обратно.

## Установка зависимостей

Кодеку нужны две npm-библиотеки: `fzstd` и `zstd-codec`.

```bash
cd vendor
npm install
```

Node 18+ (проверено на Node 24). `npm install` создаёт `vendor/node_modules/`;
в саму поставку пакет не входит.

## Как вызвать

```bash
node tools/color/make_drx.js examples/drx_spec.example.json out.drx
```

`tools/color/make_drx.js` — тонкая обёртка: читает спецификацию, подставляет
метаданные (`label: "Grade"`, 3840×2160, `resolveVersion: "21.1.1"`) и пишет DRX.

Формат спецификации:

```json
{
  "nodes": [ { "id": "node1", "type": "primary", "...": "..." } ],
  "connections": [ { "from": "node1", "to": "node2" } ],
  "metadata": { "label": "Grade", "width": 3840, "height": 2160 }
}
```

Пример рабочей спецификации — `examples/drx_spec.example.json`.
Результат: JSON в stdout с `ok`, `bytes`, `nodes`, `connections`.

Смоук-тест кодека (три DRX: primary, primary + power window, несколько нод):

```bash
node tools/color/drx_lab/gen_drx_test.js <папка для результата>
```

## Лицензия и атрибуция

* Код в `vendor/resolve-mcp-advanced/` — MIT, © авторы `samuelgursky/davinci-resolve-mcp`.
* При публикации производных материалов, использующих эти кодеки, атрибуция
  не обязательна, но приветствуется. Подробности — `docs/LEGAL_ASSETS.md`.
