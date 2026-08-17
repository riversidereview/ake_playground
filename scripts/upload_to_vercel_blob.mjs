import { put } from '@vercel/blob';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const IMAGES_DIR = path.resolve(__dirname, '../endfield-logs/apps/web/public/images');
const token = process.env.BLOB_READ_WRITE_TOKEN || process.argv[2];

if (!token) {
  console.error('Error: BLOB_READ_WRITE_TOKEN is required.');
  console.error('Usage: node scripts/upload_to_vercel_blob.mjs <your_token>');
  process.exit(1);
}

function getAllFiles(dirPath, arrayOfFiles = []) {
  const files = fs.readdirSync(dirPath);
  for (const file of files) {
    const fullPath = path.join(dirPath, file);
    if (fs.statSync(fullPath).isDirectory()) {
      arrayOfFiles = getAllFiles(fullPath, arrayOfFiles);
    } else if (file.endsWith('.png') || file.endsWith('.webp') || file.endsWith('.jpg')) {
      arrayOfFiles.push(fullPath);
    }
  }
  return arrayOfFiles;
}

async function main() {
  if (!fs.existsSync(IMAGES_DIR)) {
    console.error(`Images directory not found: ${IMAGES_DIR}`);
    return;
  }

  const files = getAllFiles(IMAGES_DIR);
  console.log(`Found ${files.length} local images ready for upload.`);
  console.log(`Targeting Vercel Blob with token: ${token.slice(0, 15)}...`);

  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < files.length; i++) {
    const filePath = files[i];
    const relPath = path.relative(IMAGES_DIR, filePath).replace(/\\/g, '/');
    const pathname = `images/${relPath}`;
    const fileBuffer = fs.readFileSync(filePath);

    try {
      const blob = await put(pathname, fileBuffer, {
        access: 'public',
        token: token,
        addRandomSuffix: false,
      });
      successCount++;
      if (successCount % 20 === 0 || i === files.length - 1) {
        console.log(`[${i + 1}/${files.length}] Uploaded: ${pathname} -> ${blob.url}`);
      }
    } catch (err) {
      failCount++;
      console.error(`Failed to upload ${pathname}:`, err.message);
    }
  }

  console.log(`\n🎉 Upload finished! Successfully uploaded: ${successCount}, Failed: ${failCount}`);
}

main().catch(console.error);
