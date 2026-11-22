/**
 * The new-task dialog's draft (T2493): a refusal ("bad token" after a server restart), the page's reload on a new
 * build or a killed browser must not lose a task being written. The text, the repo picks and whether the dialog
 * was open go to localStorage on every change (synchronous, so a kill loses nothing typed); the files go to
 * IndexedDB as they are (a Blob stays on disk there, up to the 500 MB a task may carry) whenever the list changes.
 * Only a task that went out clears it; an empty text with no files is no draft. Storage that is blocked or full
 * only means no draft: the dialog never fails over it.
 */
import { z } from "zod";

const KEY = "todoimpl.newtask.draft";
const DB = "todoimpl-newtask";
const STORE = "draft";
const FILES = "files";
const STATE = "state";

const chooserState = z.object({
  folded: z.boolean(),
  picked: z.array(z.string()),
  scope: z.enum(["all", "none", "some"]).nullable(),
  typed: z.string(),
});
/** `at` (ms) stamps each save, so the fresher of localStorage's and IndexedDB's copy wins. */
const stored = z.object({ at: z.number().optional(), body: z.string(), chooser: chooserState, open: z.boolean() });
export type ChooserState = z.infer<typeof chooserState>;
export type DraftState = z.infer<typeof stored>;

/** One attached file and whether it is a numbered image (`[Image #N]` in the text). */
export interface DraftFile {
  file: File;
  image: boolean;
}

export function loadState(): DraftState | null {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw === null ? null : stored.safeParse(JSON.parse(raw));
    return parsed?.success === true ? parsed.data : null;
  } catch {
    return null;
  }
}

function saveState(state: DraftState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Blocked or full: the draft then lives only in the open page.
  }
}

export function dropState(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // Nothing was stored, so there is nothing to drop.
  }
}

/** Runs one request on the files store; rejects when IndexedDB is missing or the open or the transaction fails. */
async function run<T>(mode: IDBTransactionMode, act: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const opening = indexedDB.open(DB, 1);
  const database = await new Promise<IDBDatabase>((resolve, reject) => {
    opening.onupgradeneeded = () => { opening.result.createObjectStore(STORE); };
    opening.onsuccess = () => { resolve(opening.result); };
    opening.addEventListener("error", () => { reject(new Error("indexedDB open failed", { cause: opening.error })); });
  });
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = database.transaction(STORE, mode);
      const request = act(tx.objectStore(STORE));
      tx.oncomplete = () => { resolve(request.result); };
      tx.addEventListener("error", () => { reject(new Error("indexedDB write failed", { cause: tx.error })); });
    });
  } finally {
    database.close();
  }
}

const isFile = (value: unknown): value is DraftFile =>
  typeof value === "object" && value !== null && (value as DraftFile).file instanceof Blob && typeof (value as DraftFile).image === "boolean";

/** The saved draft: its text state (null when none) and its files, both empty when storage fails. */
export async function loadKept(): Promise<{ files: DraftFile[]; state: DraftState | null }> {
  try {
    const files: unknown = await run("readonly", (store) => store.get(FILES));
    const state: unknown = await run("readonly", (store) => store.get(STATE));
    const parsed = stored.safeParse(state);
    return { files: Array.isArray(files) ? files.filter(isFile) : [], state: parsed.success ? parsed.data : null };
  } catch {
    return { files: [], state: null };
  }
}

/** Stores `value` under `key`; null removes it. A failure leaves the rest of the draft standing. */
async function put(key: string, value: unknown): Promise<void> {
  try {
    if (value === null) await run("readwrite", (store) => store.delete(key));
    else await run("readwrite", (store) => store.put(value, key));
  } catch {
    // Blocked, missing or full: this part lives only in the open page (and localStorage).
  }
}

/** Saves `files` as the draft's files; [] removes them. */
export const keepFiles = async (files: readonly DraftFile[]): Promise<void> => put(FILES, files.length > 0 ? files.map(({ file, image }) => ({ file, image })) : null);

/**
 * The dialog's link to its draft: `keep` on every change, `load` once. IndexedDB gets the text state too:
 * Chromium commits localStorage seconds late, so a browser killed right after typing kept only the files.
 * Nothing is written there before `load` has read it.
 */
export class DraftKeeper {
  #ready = false;
  #saved: readonly DraftFile[] = [];
  #state = "";

  keep(state: DraftState, files: readonly DraftFile[]): void {
    const isEmpty = state.body.trim() === "" && files.length === 0;
    const stamped = { ...state, at: Date.now() };
    if (isEmpty) dropState();
    else saveState(stamped);
    if (!this.#ready) return;
    const text = isEmpty ? "" : JSON.stringify(state);
    if (text !== this.#state) void put(STATE, isEmpty ? null : stamped);
    this.#state = text;
    const isSame = files.length === this.#saved.length && files.every((f, index) => f.file === this.#saved[index]?.file && f.image === this.#saved[index].image);
    if (isSame) return;
    this.#saved = files.map(({ file, image }) => ({ file, image }));
    void keepFiles(files);
  }

  async load(): Promise<{ files: DraftFile[]; state: DraftState | null }> {
    const kept = await loadKept();
    this.#saved = kept.files;
    this.#state = kept.state === null ? "" : JSON.stringify({ ...kept.state, at: undefined });
    this.#ready = true;
    return kept;
  }
}
