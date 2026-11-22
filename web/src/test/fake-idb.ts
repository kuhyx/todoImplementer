/**
 * A small in-memory IndexedDB for the new-task draft tests. Values are kept by reference: jsdom's File does not
 * survive Node's structured clone, and the browser keeps a stored Blob on disk anyway. `fail` makes the next open
 * or transaction fail, so the draft's error paths run.
 */
import { vi } from "vitest";

type Fail = "" | "open" | "tx";

interface Request {
  addEventListener: (type: "error", listener: () => void) => void;
  error: Error | null;
  failed: (() => void) | null;
  onsuccess: (() => void) | null;
  onupgradeneeded?: (() => void) | null;
  result: unknown;
}

export const fakeIdb = { fail: "" as Fail, stores: new Map<string, Map<IDBValidKey, unknown>>() };

const later = (run: () => void): void => {
  queueMicrotask(run);
};

function request(result?: unknown): Request {
  const made: Request = { addEventListener: (_type, listener) => { made.failed = listener; }, error: null, failed: null, onsuccess: null, result };
  return made;
}

function transaction(name: string): unknown {
  const isFailing = fakeIdb.fail === "tx";
  const kept = fakeIdb.stores.get(name) ?? new Map<IDBValidKey, unknown>();
  const map = isFailing ? new Map(kept) : kept; // a failed transaction writes nothing
  const tx = {
    addEventListener: (_type: "error", listener: () => void): void => { tx.failed = listener; },
    error: null as Error | null,
    failed: null as (() => void) | null,
    objectStore: () => store,
    oncomplete: null as (() => void) | null,
  };
  const store = {
    delete: (key: IDBValidKey) => request(map.delete(key)),
    get: (key: IDBValidKey) => request(map.get(key)),
    put: (value: unknown, key: IDBValidKey) => request(map.set(key, value)),
  };
  later(() => {
    if (isFailing) {
      fakeIdb.fail = "";
      tx.error = new Error("tx failed");
      tx.failed?.();
    } else tx.oncomplete?.();
  });
  return tx;
}

const database = {
  close: (): void => undefined,
  createObjectStore: (name: string): void => {
    fakeIdb.stores.set(name, new Map());
  },
  transaction,
};

function open(): Request {
  const request_ = request();
  later(() => {
    if (fakeIdb.fail === "open") {
      fakeIdb.fail = "";
      request_.error = new Error("open failed");
      request_.failed?.();
      return;
    }
    request_.result = database;
    if (fakeIdb.stores.size === 0) request_.onupgradeneeded?.();
    request_.onsuccess?.();
  });
  return request_;
}

/** Puts an empty fake on `globalThis.indexedDB` (undone by `vi.unstubAllGlobals`). */
export function installFakeIdb(): void {
  fakeIdb.fail = "";
  fakeIdb.stores.clear();
  vi.stubGlobal("indexedDB", { open });
}
