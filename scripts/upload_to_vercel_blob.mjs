import fs from 'fs';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const IMAGES_DIR = path.resolve(__dirname, '../endfield-logs/apps/web/public/images');
const token = process.env.BLOB_READ_WRITE_TOKEN || process.argv[2];

async function loadPut() {
  try {
    const mod = await import('@vercel/blob');
    return mod.put;
  } catch {
    const fallbackPath = path.resolve(__dirname, '../endfield-logs/apps/web/node_modules/@vercel/blob/dist/index.js');
    if (fs.existsSync(fallbackPath)) {
      const mod = await import(pathToFileURL(fallbackPath).href);
      return mod.put;
    }
    throw new Error("Could not find '@vercel/blob'. Please run 'pnpm install' in endfield-logs/apps/web.");
  }
}

if (!token) {
  console.log('----------------------------------------------------');
  console.log('Upload All Downloaded Assets to Vercel Blob');
  console.log('----------------------------------------------------');
  console.log('Usage:');
  console.log('  node scripts/upload_to_vercel_blob.mjs <BLOB_READ_WRITE_TOKEN>');
  console.log('Or set environment variable:');
  console.log('  $env:BLOB_READ_WRITE_TOKEN="vercel_blob_rw_..."');
  console.log('  node scripts/upload_to_vercel_blob.mjs');
  console.log('----------------------------------------------------');
  process.exit(1);
}

function getAllFiles(dirPath, arrayOfFiles = []) {
  if (!fs.existsSync(dirPath)) return arrayOfFiles;
  const files = fs.readdirSync(dirPath);
  for (const file of files) {
    const fullPath = path.join(dirPath, file);
    if (fs.statSync(fullPath).isDirectory()) {
      arrayOfFiles = getAllFiles(fullPath, arrayOfFiles);
    } else {
      const ext = path.extname(file).toLowerCase();
      if (['.png', '.webp', '.jpg', '.jpeg', '.svg', '.gif'].includes(ext)) {
        arrayOfFiles.push(fullPath);
      }
    }
  }
  return arrayOfFiles;
}

function getContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case '.png': return 'image/png';
    case '.webp': return 'image/webp';
    case '.jpg':
    case '.jpeg': return 'image/jpeg';
    case '.svg': return 'image/svg+xml';
    case '.gif': return 'image/gif';
    default: return 'application/octet-stream';
  }
}

async function uploadFile(put, filePath, token, maxRetries = 3) {
  const relPath = path.relative(IMAGES_DIR, filePath).replace(/\\/g, '/');
  const pathname = `images/${relPath}`;
  const fileBuffer = fs.readFileSync(filePath);
  const contentType = getContentType(filePath);

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const blob = await put(pathname, fileBuffer, {
        access: 'public',
        token: token,
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType: contentType,
      });
      return { ok: true, pathname, url: blob.url };
    } catch (err) {
      if (attempt === maxRetries) {
        return { ok: false, pathname, error: err.message };
      }
      await new Promise((r) => setTimeout(r, attempt * 1000));
    }
  }
}

async function main() {
  const put = await loadPut();

  if (!fs.existsSync(IMAGES_DIR)) {
    console.error(`Images directory not found: ${IMAGES_DIR}`);
    return;
  }

  const files = getAllFiles(IMAGES_DIR);
  console.log(`Found ${files.length} local images ready for upload.`);
  console.log(`Targeting Vercel Blob with token: ${token.slice(0, 15)}...`);

  const CONCURRENCY = 12;
  let successCount = 0;
  let failCount = 0;
  let currentIndex = 0;

  async function worker() {
    while (currentIndex < files.length) {
      const index = currentIndex++;
      const filePath = files[index];
      const res = await uploadFile(put, filePath, token);
      if (res.ok) {
        successCount++;
      } else {
        failCount++;
        console.error(`[FAIL] ${res.pathname}: ${res.error}`);
      }
      if ((successCount + failCount) % 25 === 0 || (successCount + failCount) === files.length) {
        console.log(`Progress: [${successCount + failCount}/${files.length}] - ${successCount} uploaded, ${failCount} failed`);
      }
    }
  }

  const workers = Array.from({ length: CONCURRENCY }, () => worker());
  await Promise.all(workers);

  console.log(`\n🎉 Upload finished! Successfully uploaded: ${successCount}, Failed: ${failCount}`);
}

main().catch(console.error);
