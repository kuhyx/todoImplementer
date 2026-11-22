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

const chooserState = z.object({
  folded: z.boolean(),
  picked: z.array(z.string()),
  scope: z.enum(["all", "none", "some"]).nullable(),
  typed: z.string(),
});
const stored = z.object({ body: z.string(), chooser: chooserState, open: z.boolean() });
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

/** The saved files, [] when there are none or storage fails. */
export async function loadFiles(): Promise<DraftFile[]> {
  try {
    const found: unknown = await run("readonly", (store) => store.get(FILES));
    return Array.isArray(found) ? found.filter(isFile) : [];
  } catch {
    return [];
  }
}

/** Saves `files` as the draft's files; [] removes them. A failure leaves the text draft standing. */
export async function keepFiles(files: readonly DraftFile[]): Promise<void> {
  try {
    const list = files.map(({ file, image }) => ({ file, image }));
    if (list.length > 0) await run("readwrite", (store) => store.put(list, FILES));
    else await run("readwrite", (store) => store.delete(FILES));
  } catch {
    // Blocked, missing or full: the files live only in the open page.
  }
}

/** The dialog's link to its draft: `keep` on every change, `files` once (no file write before that read is in). */
export class DraftKeeper {
  #ready = false;
  #saved: readonly DraftFile[] = [];

  keep(state: DraftState, files: readonly DraftFile[]): void {
    if (state.body.trim() === "" && files.length === 0) dropState();
    else saveState(state);
    const isSame = files.length === this.#saved.length && files.every((f, index) => f.file === this.#saved[index]?.file && f.image === this.#saved[index].image);
    if (isSame || !this.#ready) return;
    this.#saved = files.map(({ file, image }) => ({ file, image }));
    void keepFiles(files);
  }

  async files(): Promise<DraftFile[]> {
    const found = await loadFiles();
    this.#saved = found;
    this.#ready = true;
    return found;
  }
}
