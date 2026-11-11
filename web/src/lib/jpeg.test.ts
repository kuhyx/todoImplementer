import { afterEach, describe, expect, it, vi } from "vitest";

import { encodeJpeg, fitSize, MAX_SIDE, QUALITY, toBase64 } from "@/lib/jpeg";

interface Drawn {
  args: unknown[];
}

function stubCanvas(blob: Blob | null, hasContext = true): Drawn {
  const drawn: Drawn = { args: [] };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => (hasContext ? ({ drawImage: (...arguments_: unknown[]) => { drawn.args = arguments_; } } as unknown as CanvasRenderingContext2D) : null),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (callback: BlobCallback, type?: string, quality?: unknown) {
    drawn.args.push(type, quality);
    callback(blob);
  });
  return drawn;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("fitSize", () => {
  it("keeps small pictures and caps the longest side", () => {
    expect(fitSize(800, 600)).toEqual({ height: 600, width: 800 });
    expect(fitSize(5120, 2880)).toEqual({ height: 1440, width: MAX_SIDE });
    expect(fitSize(3000, 6000)).toEqual({ height: MAX_SIDE, width: 1280 });
  });
});

describe("toBase64", () => {
  it("encodes bytes, also past one chunk", async () => {
    await expect(toBase64(new Blob([new Uint8Array([0xFF, 0xD8, 0xFF])]))).resolves.toBe("/9j/");
    const big = new Uint8Array(70_000);
    big.fill(65);
    await expect(toBase64(new Blob([big]))).resolves.toBe(btoa("A".repeat(70_000)));
  });
});

describe("encodeJpeg", () => {
  it("draws the picture scaled into a canvas and asks for a JPEG at the set quality", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", vi.fn(() => Promise.resolve({ close, height: 3000, width: 4000 })));
    const drawn = stubCanvas(new Blob([new Uint8Array([0xFF, 0xD8, 0xFF])], { type: "image/jpeg" }));
    await expect(encodeJpeg(new Blob(["png"]))).resolves.toBe("/9j/");
    expect(drawn.args.slice(1)).toEqual([0, 0, MAX_SIDE, 1920, "image/jpeg", QUALITY]);
    expect(close).toHaveBeenCalledOnce();
  });

  it("fails when the browser cannot draw or encode", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn(() => Promise.resolve({ close: vi.fn(), height: 1, width: 1 })));
    stubCanvas(null, false);
    await expect(encodeJpeg(new Blob(["x"]))).rejects.toThrow("canvas");
    vi.restoreAllMocks();
    stubCanvas(null);
    await expect(encodeJpeg(new Blob(["x"]))).rejects.toThrow("JPEG");
  });
});
