import { describe, expect, it, vi } from "vitest";

import { h, must } from "@/lib/dom";

describe("h", () => {
  it("builds elements with text, attrs, handlers and children", () => {
    const click = vi.fn();
    const element = h(
      "button",
      { attrs: { "aria-busy": true, "aria-pressed": false, "data-x": undefined, hidden: false, n: 3, skip: null }, class: "a b", on: { click }, text: "go" },
      " tail",
      h("i"),
      false,
      null,
      undefined,
    );
    element.click();
    expect(click).toHaveBeenCalledOnce();
    expect(element.outerHTML).toBe('<button class="a b" aria-busy="true" aria-pressed="false" n="3">go tail<i></i></button>');
  });

  it("never parses markup in text", () => {
    const element = h("p", { text: "<img src=x onerror=alert(1)>" });
    expect(element.querySelector("img")).toBeNull();
    expect(element.textContent).toBe("<img src=x onerror=alert(1)>");
  });

  it("must finds or throws", () => {
    const root = h("div", {}, h("span", { class: "x" }));
    expect(must(root, ".x").tagName).toBe("SPAN");
    expect(() => must(root, ".y")).toThrow("missing element: .y");
  });

  it("defaults props", () => {
    expect(h("hr").outerHTML).toBe("<hr>");
  });
});
