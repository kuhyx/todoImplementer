import { describe, expect, it } from "vitest";

import { renderCard, statusChip } from "@/components/card";
import { STATUS_ICON } from "@/components/umbrella";
import { taskCard } from "@/lib/schemas-common";
import { preset } from "@/test/fixture-presets";
import { makeCards, NOW } from "@/test/fixtures";

const base = makeCards()[0]!;

describe("app errors on the board", () => {
  it("[T2023] shows the status the server computed for a fix that waits for the phone", () => {
    const waiting = { ...base, ...preset("waiting_phone_update", true) };
    expect(taskCard.parse(waiting)).toEqual(waiting);
    const element = renderCard(waiting, NOW);
    expect(element.dataset.status).toBe("waiting_phone_update");
    expect(element.querySelector(".card-current")?.textContent).toBe("wait for phone to connect, then update the app");
    expect(statusChip("waiting_phone_update").textContent).toBe("Waiting for phone");
    expect(STATUS_ICON.waiting_phone_update).toBe("queued");
  });

  it("[T2024] badges a card that holds app-error tickets with an icon and a count", () => {
    const marked = { ...base, app_error: 2 };
    expect(taskCard.parse(marked)).toEqual(marked);
    const badge = renderCard(marked, NOW).querySelector("[data-app-error]");
    expect(badge?.getAttribute("aria-label")).toBe("App error 2");
    expect(badge?.querySelector("svg")).not.toBeNull();
    expect(renderCard(base, NOW).querySelector("[data-app-error]")).toBeNull();
  });
});
