import { trapTab } from "@/components/drawer-shell";
/**
 * <ti-new-task>: kuhy's own task for a repo. The + button opens a dialog (repo from the board's repos or typed
 * owner/name, title, details, pictures by picker, camera, paste or drop). Create posts it; the server adds the
 * section, presses the repo card's Start and answers the card, which the app then opens. While the post runs
 * both buttons are disabled with the reason; after 1 s a loader names what it waits on.
 */
import { loader, showToast, SLOW_MS } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { buildForm, type Form, renderThumbs } from "@/components/new-task-form";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { encodeJpeg } from "@/lib/jpeg";
import { MAX_IMAGES, postNewTask, REPO } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";

export { MAX_IMAGES } from "@/lib/newtask-api";

const BUSY = "Creating the task…";
const PREPARING = "Preparing the pictures…";
const INCOMPLETE = "Needs a repo (owner/name) and a title";
const FULL = `${String(MAX_IMAGES)} pictures at most`;

function block(button: HTMLButtonElement, reason: null | string, label: string): void {
  button.setAttribute("aria-disabled", String(reason !== null));
  button.title = reason ?? label;
}

export class TiNewTask extends HTMLElement {
  #busy = false;
  readonly #form: Form;
  #images: string[] = [];
  readonly #opener: HTMLButtonElement;
  #pending = 0;
  #repos = "";
  #slow = false;
  defaultRepo = "";
  encode: (file: Blob) => Promise<string> = encodeJpeg;

  constructor() {
    super();
    this.#opener = iconButton("plus", "New task", { "data-new-task": "open" }, () => { this.#open(); });
    this.#form = buildForm({
      onClose: () => { this.#close(); },
      onFiles: (files) => { this.#add(files); },
      onInput: () => { this.#paint(); },
      onKey: (event) => { this.#onKey(event); },
      onPick: () => { if (this.#images.length + this.#pending < MAX_IMAGES) this.#form.picker.click(); },
      onSubmit: () => void this.#submit(),
    });
  }

  #open(): void {
    if (this.#busy) return;
    const form = this.#form;
    if (form.repo.value === "") form.repo.value = this.defaultRepo;
    form.panel.hidden = false;
    this.#paint();
    (form.repo.value === "" ? form.repo : form.title).focus();
  }

  #close(): void {
    this.#form.panel.hidden = true;
    this.#opener.focus();
  }

  #onKey(event: KeyboardEvent): void {
    if (event.key === "Escape") this.#close();
    else if (event.key === "Tab") trapTab(event, this.#form.dialog);
  }

  #add(files: readonly File[]): void {
    const room = Math.max(0, MAX_IMAGES - this.#images.length - this.#pending);
    for (const file of files.slice(0, room)) void this.#encodeOne(file);
    this.#paint();
  }

  async #encodeOne(file: File): Promise<void> {
    this.#pending += 1;
    try {
      this.#images.push(await this.encode(file));
    } catch (error) {
      showToast(errorText(error), "error");
    }
    this.#pending -= 1;
    this.#paint();
  }

  #reason(): null | string {
    if (this.#busy) return BUSY;
    if (this.#pending > 0) return PREPARING;
    const { repo, title } = this.#form;
    return REPO.test(repo.value) && title.value.trim() !== "" ? null : INCOMPLETE;
  }

  #paint(): void {
    const form = this.#form;
    block(form.submit, this.#reason(), "Create and start");
    form.submit.setAttribute("aria-busy", String(this.#busy));
    block(this.#opener, this.#busy ? BUSY : null, "New task");
    block(form.pick, this.#images.length + this.#pending >= MAX_IMAGES ? FULL : null, "Add pictures (or paste, or drop them here)");
    renderThumbs(form, this.#images, (index) => { this.#images.splice(index, 1); this.#paint(); });
    form.slot.replaceChildren(...(this.#busy && this.#slow ? [loader(`Waiting for ${routes.ownTask}: the todo app adds the task, then its card starts…`)] : []));
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
      const request = { body: form.body.value, images: this.#images.map((data) => ({ data_b64: data })), repo: form.repo.value, title: form.title.value.trim() };
      const created = await postNewTask(request, csrf);
      form.title.value = "";
      form.body.value = "";
      this.#images = [];
      form.panel.hidden = true;
      this.dispatchEvent(new CustomEvent("task-created", { bubbles: true, detail: { id: created.task.id } }));
    } catch (error) {
      showToast(errorText(error), "error");
      form.dialog.classList.add("nt-shake");
    }
    clearTimeout(timer);
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
