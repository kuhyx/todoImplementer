import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createPhoneTools, type PhoneTools } from "@/phone/phone-tools";

let tools: PhoneTools;
const button = (): HTMLButtonElement => {
  const found = document.querySelector<HTMLButtonElement>('[data-phone="install"]');
  if (found === null) throw new Error("no install button");
  return found;
};

function offer(): { event: Event; prompt: ReturnType<typeof vi.fn> } {
  const prompt = vi.fn(() => Promise.resolve());
  const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), { prompt });
  return { event, prompt };
}

function standalone(isStandalone: boolean): void {
  vi.mocked(matchMedia).mockImplementation((query: string) => ({ matches: isStandalone && query.includes("standalone") }) as MediaQueryList);
}

beforeEach(() => {
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok">';
  tools = createPhoneTools();
  document.body.append(tools.el);
});

afterEach(() => {
  tools.dispose();
  document.body.replaceChildren();
  standalone(false);
});

describe("install button", () => {
  it("is hidden until the browser offers the install, and the whole strip with it", () => {
    expect(button().hidden).toBe(true);
    expect(tools.el.hidden).toBe(true);
  });

  it("appears on beforeinstallprompt, calls prompt() on tap, then goes away", async () => {
    const { event, prompt } = offer();
    dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(button().hidden).toBe(false);
    expect(tools.el.hidden).toBe(false);
    expect(button().title).toBe("Install the app");
    button().click();
    await vi.waitFor(() => { expect(prompt).toHaveBeenCalledOnce(); });
    expect(button().hidden).toBe(true);
  });

  it("goes away after appinstalled", () => {
    dispatchEvent(offer().event);
    expect(button().hidden).toBe(false);
    dispatchEvent(new Event("appinstalled"));
    expect(button().hidden).toBe(true);
  });

  it("stays hidden when the page already runs standalone", () => {
    standalone(true);
    dispatchEvent(offer().event);
    expect(button().hidden).toBe(true);
  });

  it("hides if the page turns standalone after the offer", () => {
    dispatchEvent(offer().event);
    expect(button().hidden).toBe(false);
    standalone(true);
    dispatchEvent(new Event("appinstalled"));
    expect(button().hidden).toBe(true);
  });

  it("stops listening once disposed", () => {
    tools.dispose();
    dispatchEvent(offer().event);
    expect(button().hidden).toBe(true);
  });
});
