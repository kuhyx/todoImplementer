import { afterEach, describe, expect, it } from "vitest";

import type { ActivityEvent } from "@/lib/schemas";

import { createFeed, FEED_CAP } from "@/components/feed-view";

// 2026-11-19 12:34:56 UTC is 13:34:56 in Warsaw (CET, UTC+1).
const AT = Date.UTC(2026, 10, 19, 12, 34, 56) / 1000;
const ORIGINAL_TZ = process.env.TZ;

const event = (seq: number, text: string, at = AT + seq): ActivityEvent => ({ at, kind: "result", seq, text, tool: null, type: "activity" });
const texts = (feed: ReturnType<typeof createFeed>): string[] => [...feed.el.querySelectorAll(".feed-text")].map((n) => n.textContent);

afterEach(() => {
  if (ORIGINAL_TZ === undefined) delete process.env.TZ;
  else process.env.TZ = ORIGINAL_TZ;
});

describe("feed order and clock", () => {
  it("[T2099] lists the newest activity first", () => {
    const feed = createFeed();
    for (const item of [event(1, "one"), event(2, "two"), event(3, "three")]) feed.append(item);
    expect(texts(feed)).toEqual(["three", "two", "one"]);
  });

  it("[T2099] keeps the newest lines when the cap drops old ones", () => {
    const feed = createFeed();
    for (let seq = 1; seq <= FEED_CAP + 2; seq += 1) feed.append(event(seq, `n${String(seq)}`));
    const list = texts(feed);
    expect(list).toHaveLength(FEED_CAP);
    expect(list[0]).toBe(`n${String(FEED_CAP + 2)}`);
    expect(list.at(-1)).toBe("n3");
  });

  it("[T2100] shows each time in the viewer's timezone, not UTC", () => {
    process.env.TZ = "Europe/Warsaw";
    const feed = createFeed();
    feed.append(event(1, "x", AT));
    expect(feed.el.querySelector(".feed-time")?.textContent).toBe("13:34:56");
  });
});
