// Image preparer: shrink a phone photo before upload and strip its metadata.
// createImageBitmap applies the camera's orientation flag; re-encoding through a canvas keeps
// pixels only, so EXIF (including GPS location) never leaves the device.

export const MAX_EDGE = 2000;
export const QUALITY = 0.85;

export function targetSize(width: number, height: number, maxEdge = MAX_EDGE) {
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

export async function prepareImage(file: File): Promise<Blob> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    // Formats the browser cannot decode (e.g. some HEIC): send as-is; the server validates
    // the content and strips metadata itself.
    return file;
  }
  const { width, height } = targetSize(bitmap.width, bitmap.height);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return file;
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', QUALITY),
  );
  return blob ?? file;
}
