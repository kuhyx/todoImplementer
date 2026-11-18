import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom has no matchMedia; the install button asks whether the page runs standalone. Tests override `matches`.
Object.defineProperty(globalThis, "matchMedia", {
  configurable: true,
  value: vi.fn((query: string) => ({ addEventListener: vi.fn(), matches: false, media: query, removeEventListener: vi.fn() })),
  writable: true,
});

// jsdom has no scrollIntoView; the new-task dialog keeps its growing details field in view with it.
Element.prototype.scrollIntoView = vi.fn();
