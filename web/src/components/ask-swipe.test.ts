/** Pointer swipes: right and left, short moves, buttons, mouse drags in a textarea and cancelled gestures. */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { attachSwipe } from "@/components/ask-swipe";

const fire = (target: Element, type: string, x = 0, y = 0, pointerType = "touch"): void => {
  target.dispatchEvent(Object.assign(new Event(type, { bubbles: true }), { clientX: x, clientY: y, pointerType }));
};
const onSwipe = vi.fn();
let area: HTMLElement;

beforeEach(() => {
  onSwipe.mockReset();
  document.body.innerHTML = '<section id="a"><button id="b">b</button><textarea id="t"></textarea><p id="p">p</p></section>';
  area = document.querySelector<HTMLElement>("#a")!;
  attachSwipe(area, onSwipe);
});

const drag = (target: string, dx: number, dy = 0, type = "touch"): void => {
  const element = document.querySelector(target)!;
  fire(element, "pointerdown", 100, 100, type);
  fire(element, "pointerup", 100 + dx, 100 + dy, type);
};

describe("swipe", () => {
  it("swipes right to next and left to back", () => {
    drag("#p", 120);
    expect(onSwipe).toHaveBeenLastCalledWith("next");
    drag("#p", -120);
    expect(onSwipe).toHaveBeenLastCalledWith("back");
  });

  it("ignores short and vertical moves", () => {
    drag("#p", 40);
    drag("#p", 120, 100);
    expect(onSwipe).not.toHaveBeenCalled();
  });

  it("ignores a drag that started on a button or a mouse drag in the textarea", () => {
    drag("#b", 150);
    drag("#t", 150, 0, "mouse");
    expect(onSwipe).not.toHaveBeenCalled();
    drag("#t", 150, 0, "touch");
    expect(onSwipe).toHaveBeenCalledTimes(1);
  });

  it("needs a pointerdown first and forgets a cancelled gesture", () => {
    fire(area, "pointerup", 300, 0);
    fire(area, "pointerdown", 0, 0);
    fire(area, "pointercancel");
    fire(area, "pointerup", 300, 0);
    expect(onSwipe).not.toHaveBeenCalled();
  });

  it("treats a non-element target as a plain start", () => {
    const text = document.createTextNode("t");
    area.append(text);
    text.dispatchEvent(Object.assign(new Event("pointerdown", { bubbles: true }), { clientX: 0, clientY: 0, pointerType: "touch" }));
    fire(area, "pointerup", 200, 0);
    expect(onSwipe).toHaveBeenCalledWith("next");
  });
});
