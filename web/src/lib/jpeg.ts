/**
 * Every picture becomes a JPEG in the browser (the todo app stores only .jpg and the server stays stdlib-only):
 * decoded with createImageBitmap (camera EXIF rotation applied), drawn into a canvas with the longest side
 * capped, encoded at QUALITY, then base64 for the JSON body.
 */
export const MAX_SIDE = 2560;
export const QUALITY = 0.85;
const CHUNK = 0x80_00;

export function fitSize(width: number, height: number): { height: number; width: number } {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  return { height: Math.round(height * scale), width: Math.round(width * scale) };
}

export async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let start = 0; start < bytes.length; start += CHUNK) binary += String.fromCodePoint(...bytes.subarray(start, start + CHUNK));
  return btoa(binary);
}

export async function encodeJpeg(file: Blob): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const { height, width } = fitSize(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context === null) {
    bitmap.close();
    throw new Error("this browser cannot draw a picture into a canvas");
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const jpeg = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", QUALITY);
  });
  if (jpeg === null) throw new Error("the browser could not encode the picture as JPEG");
  return toBase64(jpeg);
}
