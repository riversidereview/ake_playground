import fs from 'fs';
import path from 'path';
import https from 'https';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_DIR = path.resolve(__dirname, '../endfield-logs/apps/web/public/images');
const MANIFEST_FILE = path.resolve(__dirname, '../endfield-logs/data/required_assets_manifest.json');

const httpsAgent = new https.Agent({
  keepAlive: true,
  maxSockets: 32,
  rejectUnauthorized: false,
});

async function downloadUrl(url) {
  return new Promise((resolve) => {
    const req = https.get(url, { agent: httpsAgent, timeout: 6000, headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
      if (res.statusCode === 200) {
        const chunks = [];
        res.on('data', (d) => chunks.push(d));
        res.on('end', () => resolve({ ok: true, data: Buffer.concat(chunks) }));
      } else {
        res.resume();
        resolve({ ok: false, status: res.statusCode });
      }
    });
    req.on('error', (e) => resolve({ ok: false, error: e.message }));
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, error: 'timeout' }); });
  });
}

async function downloadAsset(relPath) {
  const targetPath = path.join(BASE_DIR, relPath);
  if (fs.existsSync(targetPath) && fs.statSync(targetPath).size > 50) {
    return { relPath, ok: true, msg: 'cached' };
  }

  const filename = path.basename(relPath);
  const sources = [
    `https://zmdlogs.com/images/${relPath}`,
    `https://endfielddex.com/images/${relPath}`,
    `https://endfielddex.com/images/${filename}`,
  ];

  if (relPath.includes('charremoteicon')) {
    const roundName = filename.replace('icon_', 'icon_round_');
    sources.unshift(`https://zmdlogs.com/images/character/charremoteicon/${roundName}`);
    sources.splice(2, 0, `https://endfielddex.com/images/${roundName}`);
  }

  for (const url of sources) {
    const res = await downloadUrl(url);
    if (res.ok && res.data.length > 30) {
      fs.mkdirSync(path.dirname(targetPath), { recursive: true });
      fs.writeFileSync(targetPath, res.data);
      return { relPath, ok: true, msg: `ok (${res.data.length}B)` };
    }
  }

  return { relPath, ok: false, msg: 'all mirrors failed' };
}

async function main() {
  if (!fs.existsSync(MANIFEST_FILE)) {
    console.error(`Manifest not found: ${MANIFEST_FILE}`);
    process.exit(1);
  }

  const paths = JSON.parse(fs.readFileSync(MANIFEST_FILE, 'utf-8'));
  console.log(`Starting Node.js async download for ${paths.length} assets...`);

  let cached = 0;
  let downloaded = 0;
  let failed = 0;
  let currentIndex = 0;
  const CONCURRENCY = 24;

  async function worker() {
    while (currentIndex < paths.length) {
      const idx = currentIndex++;
      const p = paths[idx];
      const res = await downloadAsset(p);
      if (res.ok) {
        if (res.msg === 'cached') cached++;
        else downloaded++;
      } else {
        failed++;
      }
      const total = cached + downloaded + failed;
      if (total % 50 === 0 || total === paths.length) {
        console.log(`Progress: [${total}/${paths.length}] - ${cached} cached, ${downloaded} downloaded, ${failed} failed`);
      }
    }
  }

  const workers = Array.from({ length: CONCURRENCY }, () => worker());
  await Promise.all(workers);

  console.log('\nDownload Summary:');
  console.log(`  Cached: ${cached}`);
  console.log(`  Downloaded: ${downloaded}`);
  console.log(`  Total available: ${cached + downloaded} / ${paths.length}`);
  console.log(`  Failed: ${failed}`);
}

main().catch(console.error);
