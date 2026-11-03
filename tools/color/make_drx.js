#!/usr/bin/env node
/**
 * Генератор DRX для DaVinci Resolve.
 * Использует откалиброванный под Resolve Studio кодек
 * (samuelgursky/davinci-resolve-mcp -> resolve-advanced/vendor/drx-codec).
 *
 * Использование: node tools/color/make_drx.js <spec.json> <out.drx>
 * spec.json: { nodes: [...], connections: [...], metadata: {...} }
 */
const fs = require('node:fs');
const path = require('node:path');

// __dirname = <ПАКЕТ>/tools/color  ->  корень пакета на два уровня выше
const PACK_ROOT = path.join(__dirname, '..', '..');
const CODEC_DIR = path.join(PACK_ROOT, 'vendor', 'resolve-mcp-advanced',
  'resolve-advanced', 'vendor', 'drx-codec');
const { generateMultiNodeDRX } = require(path.join(CODEC_DIR, 'drx-generator.js'));

async function main() {
  const specPath = process.argv[2];
  const outPath = process.argv[3];
  if (!specPath || !outPath) {
    console.error('usage: node tools/color/make_drx.js <spec.json> <out.drx>');
    process.exit(2);
  }
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  const metadata = Object.assign(
    { label: 'Grade', width: 3840, height: 2160, resolveVersion: '21.1.1' },
    spec.metadata || {}
  );
  const xml = await generateMultiNodeDRX(spec.nodes, spec.connections, metadata);
  fs.writeFileSync(outPath, xml, 'utf8');
  const stat = fs.statSync(outPath);
  console.log(JSON.stringify({
    ok: true,
    out: outPath,
    bytes: stat.size,
    nodes: spec.nodes.length,
    connections: spec.connections.length,
  }));
}

main().catch((err) => {
  console.error('DRX_ERROR ' + (err && err.stack ? err.stack : String(err)));
  process.exit(1);
});
