/** Numbered images for Send to Claude and New task (contracts/requests.schema.json `image_ref`): which files qualify, and the `[Image #N]` tags. */
export const IMAGE_TYPES: readonly string[] = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MB = 1024 * 1024;
export const MAX_IMAGE = 10 * MB;
export const MAX_IMAGES = 8;
const TAG = /\[Image #(\d+)\]( ?)/gv;

/** Why `file` cannot be image number `count + 1`, or null when it can. */
export function imageProblem(file: File, count: number): null | string {
  if (!IMAGE_TYPES.includes(file.type)) return `${file.name}: not a PNG, JPEG, WebP or GIF image`;
  if (file.size > MAX_IMAGE) return `${file.name}: over ${String(MAX_IMAGE / MB)} MB`;
  return count >= MAX_IMAGES ? `${file.name}: at most ${String(MAX_IMAGES)} images per message` : null;
}

/** Put `[Image #n]` at the caret, with a space on each side unless one is already there. */
export function insertTag(box: HTMLTextAreaElement, n: number): void {
  const { selectionEnd: end, selectionStart: start, value } = box;
  const lead = start === 0 || /\s/v.test(value.charAt(start - 1)) ? "" : " ";
  const trail = /\s/v.test(value.charAt(end)) ? "" : " ";
  box.setRangeText(`${lead}[Image #${String(n)}]${trail}`, start, end, "end");
}

/** Drop the tag of image `n` (and the space after it) and move every later tag down by one. */
export function dropTag(text: string, n: number): string {
  return text.replaceAll(TAG, (_whole: string, digits: string, space: string) => {
    const at = Number(digits);
    if (at === n) return "";
    return `[Image #${String(at > n ? at - 1 : at)}]${space}`;
  });
}
