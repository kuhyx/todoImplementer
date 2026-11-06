/** Pointer-event swipes: right accepts, left goes back. Buttons never start one; a mouse drag inside a textarea selects text. */
import { swipeOf } from "@/components/ask-model";

export function attachSwipe(element: HTMLElement, onSwipe: (direction: "back" | "next") => void): void {
  let start: null | { x: number; y: number } = null;
  element.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const isBlocked = target?.closest("button") != null || (event.pointerType === "mouse" && target?.closest("textarea") != null);
    start = isBlocked ? null : { x: event.clientX, y: event.clientY };
  });
  element.addEventListener("pointerup", (event) => {
    if (start === null) return;
    const direction = swipeOf(event.clientX - start.x, event.clientY - start.y);
    start = null;
    if (direction !== null) onSwipe(direction);
  });
  element.addEventListener("pointercancel", () => {
    start = null;
  });
}
