import { describe, expect, it } from "vitest";

import { renderUsage } from "@/components/usage-strip";
import { type Board, board as boardSchema } from "@/lib/schemas";
import { makeBoard } from "@/test/fixtures";

const COMMAND = "~/src/todoImplementer/scripts/rotate_api_key.py";
type Key = NonNullable<Board["api_key"]>;
const keyField = (level: Key["level"], state: Key["state"], text: string): Key => ({ expires: "2026-12-01", level, state, text });

function paint(apiKey?: Key): HTMLElement {
  const board = { ...makeBoard(), ...(apiKey !== undefined && { api_key: apiKey }) };
  return renderUsage(null, board, null, "abc1234", 0);
}

describe("API key banner", () => {
  it("shows a red alert with the server's text when the key is expired", () => {
    const text = `Claude API key expired: expired on 2026-11-01. Run ${COMMAND}`;
    const element = paint(keyField("error", "expired", text));
    const banner = element.querySelector<HTMLElement>(".key-banner");
    expect(banner?.textContent).toBe(text);
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(banner?.dataset.state).toBe("expired");
  });

  it("shows an amber status banner when the key is expiring", () => {
    const banner = paint(keyField("warn", "expiring", `expires soon. Run ${COMMAND}`)).querySelector<HTMLElement>(".key-banner");
    expect(banner?.getAttribute("role")).toBe("status");
    expect(banner?.dataset.level).toBe("warn");
  });

  it("shows nothing when the key is ok or absent", () => {
    expect(paint(keyField("ok", "ok", "valid")).querySelector(".key-banner")).toBeNull();
    expect(paint().querySelector(".key-banner")).toBeNull();
    expect(renderUsage(null, null, null, null, 0).querySelector(".key-banner")).toBeNull();
  });

  it("the Zod mirror accepts the field and rejects an unknown state", () => {
    expect(boardSchema.safeParse({ ...makeBoard(), api_key: keyField("error", "missing", "t") }).success).toBe(true);
    expect(boardSchema.safeParse({ ...makeBoard(), api_key: { ...keyField("error", "missing", "t"), state: "weird" } }).success).toBe(false);
  });
});
