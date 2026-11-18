import { trapTab } from "@/components/drawer-shell";
/**
 * <ti-new-task>: kuhy's own task for a repo. The + button opens a dialog (repo from the board's repos or typed
 * owner/name, title, details, files of any type by picker, camera, paste or drop). Create uploads each file
 * unchanged (POST /api/upload, 100 MB each, 500 MB together), then posts the task with their ids; the server adds
 * the section, presses the repo card's Start and answers the card, which the app then opens. While that runs both
 * buttons are disabled with the reason; after 1 s a loader names what it waits on. At 640 px or less the dialog
 * fills the visible viewport (it follows `visualViewport`, so the keyboard never covers the details field).
 */
import { loader, showToast, SLOW_MS } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { type Attached, buildForm, type Form, renderThumbs } from "@/components/new-task-form";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { MAX_FILE, MAX_TOTAL, postNewTask, REPO, uploadFile } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";

const BUSY = "Creating the task…";
const INCOMPLETE = "Needs a repo (owner/name) and a title";
const MB = 1024 * 1024;

function block(button: HTMLButtonElement, reason: null | string, label: string): void {
  button.setAttribute("aria-disabled", String(reason !== null));
  button.title = reason ?? label;
}

export class TiNewTask extends HTMLElement {
  #busy = false;
  readonly #form: Form;
  #files: Attached[] = [];
  readonly #opener: HTMLButtonElement;
  #repos = "";
  #slow = false;
  #waiting: string = routes.ownTask;
  readonly #onViewport = (): void => { this.#fit(); };
  defaultRepo = "";

  constructor() {
    super();
    this.#opener = iconButton("plus", "New task", { "data-new-task": "open" }, () => { this.#open(); });
    this.#form = buildForm({
      onClose: () => { this.#close(); },
      onFiles: (files) => { this.#add(files); },
      onGrow: () => { this.#grow(); },
      onInput: () => { this.#paint(); },
      onKey: (event) => { this.#onKey(event); },
      onSubmit: () => void this.#submit(),
    });
  }

  #open(): void {
    if (this.#busy) return;
    const form = this.#form;
    if (form.repo.value === "") form.repo.value = this.defaultRepo;
    form.panel.hidden = false;
    globalThis.visualViewport?.addEventListener("resize", this.#onViewport);
    this.#fit();
    this.#paint();
    (form.repo.value === "" ? form.repo : form.title).focus();
  }

  #close(): void {
    this.#hide();
    this.#opener.focus();
  }

  #hide(): void {
    this.#form.panel.hidden = true;
    globalThis.visualViewport?.removeEventListener("resize", this.#onViewport);
  }

  /** The dialog's height and top follow the part of the page the keyboard leaves visible (CSS uses them at ≤640 px). */
  #fit(): void {
    const viewport: undefined | VisualViewport = globalThis.visualViewport ?? undefined; // jsdom has none
    if (viewport === undefined) return;
    this.#form.dialog.style.setProperty("--nt-vh", `${String(viewport.height)}px`);
    this.#form.dialog.style.setProperty("--nt-top", `${String(viewport.offsetTop)}px`);
  }

  /** The details field grows with its text; the caret line stays in view above the pinned actions. */
  #grow(): void {
    const { body } = this.#form;
    body.style.height = "auto";
    body.style.height = `${String(body.scrollHeight)}px`;
    body.scrollIntoView({ block: "nearest" });
  }

  #onKey(event: KeyboardEvent): void {
    if (event.key === "Escape") this.#close();
    else if (event.key === "Tab") trapTab(event, this.#form.dialog);
  }

  #add(files: readonly File[]): void {
    let total = this.#files.reduce((sum, { file }) => sum + file.size, 0);
    for (const file of files) {
      if (file.size > MAX_FILE || total + file.size > MAX_TOTAL) {
        const cap = file.size > MAX_FILE ? `${String(MAX_FILE / MB)} MB per file` : `${String(MAX_TOTAL / MB)} MB per task`;
        showToast(`${file.name}: over ${cap}`, "error");
        continue;
      }
      total += file.size;
      this.#files.push({ file, url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null });
    }
    this.#paint();
  }

  #remove(index: number): void {
    const [gone] = this.#files.splice(index, 1);
    if (gone?.url != null) URL.revokeObjectURL(gone.url);
    this.#paint();
  }

  /** Uploads what is not uploaded yet (a retry after a refusal sends nothing twice); answers every id in order. */
  async #upload(csrf: string): Promise<string[]> {
    for (const attached of this.#files) {
      if (attached.id !== undefined) continue;
      this.#waiting = `${routes.upload} (${attached.file.name})`;
      this.#paint();
      attached.id = await uploadFile(attached.file, csrf);
    }
    this.#waiting = routes.ownTask;
    return this.#files.map(({ id = "" }) => id);
  }

  #reason(): null | string {
    if (this.#busy) return BUSY;
    const { repo, title } = this.#form;
    return REPO.test(repo.value) && title.value.trim() !== "" ? null : INCOMPLETE;
  }

  #paint(): void {
    const form = this.#form;
    block(form.submit, this.#reason(), "Create and start");
    form.submit.setAttribute("aria-busy", String(this.#busy));
    block(this.#opener, this.#busy ? BUSY : null, "New task");
    renderThumbs(form, this.#files, (index) => { this.#remove(index); });
    const text = this.#waiting === routes.ownTask ? `Waiting for ${routes.ownTask}: the todo app adds the task, then its card starts…` : `Uploading ${this.#waiting}…`;
    form.slot.replaceChildren(...(this.#busy && this.#slow ? [loader(text)] : []));
  }

  async #submit(): Promise<void> {
    if (this.#reason() !== null) return;
    const csrf = csrfToken();
    if (csrf === null) {
      showToast("This page has no CSRF token; reload it.", "error");
      return;
    }
    const form = this.#form;
    form.dialog.classList.remove("nt-shake");
    this.#busy = true;
    this.#paint();
    const timer = setTimeout(() => { this.#slow = true; this.#paint(); }, SLOW_MS);
    try {
      const files = await this.#upload(csrf);
      const request = { body: form.body.value, ...((files.length > 0) && { files }), repo: form.repo.value, title: form.title.value.trim() };
      const created = await postNewTask(request, csrf);
      form.title.value = "";
      form.body.value = "";
      form.body.style.height = "";
      for (const { url } of this.#files) if (url !== null) URL.revokeObjectURL(url);
      this.#files = [];
      this.#hide();
      this.dispatchEvent(new CustomEvent("task-created", { bubbles: true, detail: { id: created.task.id } }));
    } catch (error) {
      showToast(errorText(error), "error");
      form.dialog.classList.add("nt-shake");
    }
    clearTimeout(timer);
    this.#waiting = routes.ownTask;
    this.#busy = false;
    this.#slow = false;
    this.#paint();
  }

  set repos(list: readonly string[]) {
    const signature = list.join("\n");
    if (signature === this.#repos) return;
    this.#repos = signature;
    this.#form.list.replaceChildren(...list.map((repo) => h("option", { attrs: { value: repo } })));
  }

  connectedCallback(): void {
    if (!this.contains(this.#opener)) this.append(this.#opener, this.#form.panel);
    this.#paint();
  }
}

export function defineNewTask(): void {
  if (!customElements.get("ti-new-task")) customElements.define("ti-new-task", TiNewTask);
}
