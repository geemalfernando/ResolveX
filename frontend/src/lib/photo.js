// Vercel functions reject request bodies over 4.5 MB and phone cameras routinely
// produce more, so oversized photos are downscaled before they reach the API.
// Evidence photos only need enough detail to compare packaging, not full sensor
// resolution.

const MAX_EDGE = 1600;
const TARGET_BYTES = 3 * 1024 * 1024;
const SUPPORTED = new Set(['image/jpeg', 'image/png', 'image/webp']);
const ATTEMPTS = [
  [MAX_EDGE, 0.82],
  [1200, 0.7],
];

function fitted(width, height, maxEdge) {
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const ratio = maxEdge / longest;
  return { width: Math.round(width * ratio), height: Math.round(height * ratio) };
}

function encode(bitmap, maxEdge, quality) {
  const { width, height } = fitted(bitmap.width, bitmap.height, maxEdge);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
}

export async function preparePhoto(file) {
  if (!file || !SUPPORTED.has(file.type) || file.size <= TARGET_BYTES) return file;

  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return file;
  }

  try {
    for (const [maxEdge, quality] of ATTEMPTS) {
      const blob = await encode(bitmap, maxEdge, quality);
      if (blob && blob.size <= TARGET_BYTES) {
        const name = `${file.name.replace(/\.[^.]+$/, '')}.jpg`;
        return new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
      }
    }
    return file;
  } finally {
    bitmap.close?.();
  }
}
