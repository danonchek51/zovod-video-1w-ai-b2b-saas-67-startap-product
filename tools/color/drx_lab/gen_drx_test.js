// gen_drx_test.js — смоук-тест вендорнутого DRX-кодека на нашей Resolve 21.1.1.
//
// Генерирует три файла:
//   drx_primary_r21.drx   — простой CDL/primary (баланс+gain+насыщенность)
//   drx_window_r21.drx    — primary + power window (окно) — то, ради чего DRX и нужен
//   drx_multinode_r21.drx — несколько нод + связь
//
// Все три — с resolveVersion: "21".
// node gen_drx_test.js [outDir]
const fs = require('fs');
const path = require('path');

// CODEC_DIR указывает на <ПАКЕТ>/vendor/resolve-mcp-advanced/resolve-advanced/vendor/drx-codec
const PACK_ROOT = path.resolve(__dirname, '..', '..', '..');
const CODEC_DIR = path.join(PACK_ROOT, 'vendor', 'resolve-mcp-advanced',
  'resolve-advanced', 'vendor', 'drx-codec');
const CODEC = path.join(CODEC_DIR, 'drx-generator.js');
const OUT = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(PACK_ROOT, 'work', 'drx_lab');

function dump(name, buf) {
  const p = path.join(OUT, name);
  fs.mkdirSync(OUT, { recursive: true });
  const isBuf = Buffer.isBuffer(buf);
  fs.writeFileSync(p, isBuf ? buf : Buffer.from(String(buf), 'utf8'));
  const head = (isBuf ? buf.toString('latin1') : String(buf)).slice(0, 160).replace(/[^\x20-\x7e]/g, '.');
  console.log('%-24s %8s bytes  head: %s', name, (isBuf ? buf.length : String(buf).length), head);
  return p;
}

(async () => {
  const codec = require(CODEC);
  console.log('codec loaded, exports:', Object.keys(codec).length);

  // 1. простой primary-грейд
  const primary = await codec.generateDRX(
    {
      lift: { r: 0.03, g: 0.03, b: 0.03 },
      gain: { r: 1.06, g: 1.0, b: 0.94 },
      offset: { r: 0, g: 0, b: 0 },
      saturation: 55,
      contrast: 1.05,
    },
    { label: 'sandbox primary R21', width: 3840, height: 2160, resolveVersion: '21' }
  );
  dump('drx_primary_r21.drx', primary);

  // 2. primary + power window (круг) — многоузловой сценарий
  let windowDrx = null;
  try {
    windowDrx = await codec.generateDRX(
      {
        lift: { r: 0.03, g: 0.03, b: 0.03 },
        gain: { r: 1.06, g: 1.0, b: 0.94 },
        window: {
          type: 'circle',
          size: 0.6, pan: 0.35, tilt: 0.75, soft: 0.05,
          gain: { r: 1.12, g: 1.08, b: 1.0 },
        },
      },
      { label: 'sandbox window R21', width: 3840, height: 2160, resolveVersion: '21' }
    );
    dump('drx_window_r21.drx', windowDrx);
  } catch (e) {
    console.log('WINDOW FAIL:', e && e.message);
  }

  // 3. мульти-нода
  try {
    const nodes = [
      codec.createNode(36, 0, 0, { lift: { r: 0.02, g: 0.02, b: 0.02 }, gain: { r: 1.04, g: 1.0, b: 0.96 } }, { resolveVersion: '21' }),
      codec.createNode(37, 200, 0, { lift: { r: 0.0, g: 0.0, b: 0.0 }, gain: { r: 1.0, g: 1.0, b: 1.0 } }, { resolveVersion: '21' }),
    ];
    const conns = [codec.createConnection(36, 37, 0)];
    const multi = await codec.generateMultiNodeDRX(nodes, conns, {
      label: 'sandbox multi R21', width: 3840, height: 2160, resolveVersion: '21',
    });
    dump('drx_multinode_r21.drx', multi);
  } catch (e) {
    console.log('MULTI FAIL:', e && e.message);
  }
})().catch((e) => {
  console.error('FATAL', e && e.stack);
  process.exit(1);
});
