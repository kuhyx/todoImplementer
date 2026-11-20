import { trapTab } from "@/components/drawer-shell";
/**
 * <ti-new-task>: kuhy's own task. The + button opens a dialog: first where it goes (RepoChooser: none, all or
 * several repos), then one description box whose first line is the title, files of any type by picker, camera,
 * paste or drop. Create sends one task per picked repo (none and all: one repo-less note that triage routes). It
 * uploads each file once, unchanged (POST /api/upload, 100 MB each, 500 MB together; the server keeps the upload
 * for the next repo, T2397), then posts each task with their ids; the server adds the section,
 * presses the repo card's Start and answers the card, which the app then opens. A repo already sent is dropped
 * from the picks, so a retry after a refusal sends nothing twice. While that runs both
 * buttons are disabled with the reason; after 1 s a loader names what it waits on. At 640 px or less the dialog
 * fills the visible viewport (it follows `visualViewport`, so the keyboard never covers the details field).
 */
import { loader, showToast, SLOW_MS } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { RepoChooser } from "@/components/new-task-chooser";
import { type Attached, buildForm, type Form, renderThumbs } from "@/components/new-task-form";
import { csrfToken } from "@/lib/boot";
import { errorText } from "@/lib/http";
import { dropTag, imageProblem, insertTag } from "@/lib/image-tags";
import { MAX_FILE, MAX_TOTAL, postNewTask, splitNote, uploadFile } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";

const BUSY = "Creating the task…";
const INCOMPLETE = "Needs a repo choice and a description";
const MB = 1024 * 1024;

function block(button: HTMLButtonElement, reason: null | string, label: string): void {
  button.setAttribute("aria-disabled", String(reason !== null));
  button.title = reason ?? label;
}

export class TiNewTask extends HTMLElement {
  #busy = false;
  readonly #chooser: RepoChooser;
  readonly #form: Form;
  #files: Attached[] = [];
  readonly #opener: HTMLButtonElement;
  #slow = false;
  #waiting: string = routes.ownTask;
  readonly #onViewport = (): void => { this.#fit(); };
  defaultRepo = "";

  constructor() {
    super();
    this.#opener = iconButton("plus", "New task", { "data-new-task": "open" }, () => { this.#open(); });
    this.#chooser = new RepoChooser((isFolded) => {
      this.#paint();
      if (isFolded) this.#form.body.focus();
    });
    this.#form = buildForm({
      onClose: () => { this.#close(); },
      onFiles: (files) => { this.#add(files); },
      onGrow: () => { this.#grow(); },
      onInput: () => { this.#paint(); },
      onKey: (event) => { this.#onKey(event); },
      onSubmit: () => void this.#submit(),
    }, this.#chooser.element);
  }

  #open(): void {
    if (this.#busy) return;
    const form = this.#form;
    if (this.#chooser.scope === null) this.#chooser.reset(this.defaultRepo);
    form.panel.hidden = false;
    globalThis.visualViewport?.addEventListener("resize", this.#onViewport);
    this.#fit();
    this.#paint();
    (this.#chooser.scope === null ? this.#chooser.typed : form.body).focus();
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
      const isImage = imageProblem(file, this.#images()) === null; // else a plain file: a big or ninth image too
      this.#files.push({ file, image: isImage, url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null });
      if (isImage) insertTag(this.#form.body, this.#images());
    }
    this.#paint();
  }

  /** How many numbered images (`[Image #N]`) the first `end` attachments hold. */
  #images(end = this.#files.length): number {
    return this.#files.slice(0, end).filter(({ image }) => image).length;
  }

  #remove(index: number): void {
    const number = this.#images(index + 1);
    const [gone] = this.#files.splice(index, 1);
    if (gone?.url != null) URL.revokeObjectURL(gone.url);
    if (gone?.image === true) this.#form.body.value = dropTag(this.#form.body.value, number);
    this.#paint();
  }

  /** Uploads what is not uploaded yet (a retry after a refusal sends nothing twice); answers images and files apart. */
  async #upload(csrf: string): Promise<{ files: string[]; images: { upload: string }[] }> {
    for (const attached of this.#files) {
      if (attached.id !== undefined) continue;
      this.#waiting = `${routes.upload} (${attached.file.name})`;
      this.#paint();
      attached.id = await uploadFile(attached.file, csrf);
    }
    this.#waiting = routes.ownTask;
    const ids = (isImage: boolean): string[] => this.#files.filter((a) => a.image === isImage).map(({ id = "" }) => id);
    return { files: ids(false), images: ids(true).map((upload) => ({ upload })) };
  }

  #reason(): null | string {
    if (this.#busy) return BUSY;
    return this.#chooser.targets().length > 0 && splitNote(this.#form.body.value).title !== "" ? null : INCOMPLETE;
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
      const { body, title } = splitNote(form.body.value);
      let made: string | undefined;
      for (const repo of this.#chooser.targets()) {
        const { files, images } = await this.#upload(csrf);
        const request = { ...(body !== "" && { body }), ...((files.length > 0) && { files }), ...((images.length > 0) && { images }), ...(repo !== null && { repo }), title };
        const created = await postNewTask(request, csrf);
        this.#chooser.sent(repo);
        made = created.task?.id ?? made;
      }
      form.body.value = "";
      form.body.style.height = "";
      for (const { url } of this.#files) if (url !== null) URL.revokeObjectURL(url);
      this.#files = [];
      this.#chooser.reset("");
      this.#hide();
      if (made !== undefined) this.dispatchEvent(new CustomEvent("task-created", { bubbles: true, detail: { id: made } }));
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
    this.#chooser.repos = list;
  }

  connectedCallback(): void {
    if (!this.contains(this.#opener)) this.append(this.#opener, this.#form.panel);
    this.#paint();
  }
}

export function defineNewTask(): void {
  if (!customElements.get("ti-new-task")) customElements.define("ti-new-task", TiNewTask);
}
