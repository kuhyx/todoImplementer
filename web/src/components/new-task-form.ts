/** The new-task dialog's DOM: icon-labelled fields (names in aria-label and title, no visible words), attachments, actions. */
import { icon, iconButton, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { MAX_BODY, MAX_TITLE } from "@/lib/newtask-api";

export interface FormHandlers {
  onClose: () => void;
  onFiles: (files: readonly File[]) => void;
  onGrow: () => void;
  onInput: () => void;
  onKey: (event: KeyboardEvent) => void;
  onSubmit: () => void;
}

export interface Form {
  body: HTMLTextAreaElement;
  camera: HTMLButtonElement;
  cancel: HTMLButtonElement;
  dialog: HTMLElement;
  list: HTMLDataListElement;
  panel: HTMLElement;
  pick: HTMLButtonElement;
  repo: HTMLInputElement;
  slot: HTMLElement;
  submit: HTMLButtonElement;
  thumbs: HTMLElement;
  title: HTMLInputElement;
}

/** One file in the dialog: `url` is its object URL when it is an image (a thumbnail), `id` once uploaded. */
export interface Attached {
  file: File;
  id?: string;
  url: null | string;
}

const LIST_ID = "nt-repos";

function row(glyph: IconName, control: HTMLElement): HTMLElement {
  return h("div", { class: "nt-row" }, h("span", { attrs: { "aria-hidden": "true" }, class: "nt-glyph" }, icon(glyph)), control);
}

const listed = (files: FileList | null | readonly File[] | undefined): File[] => [...(files ?? [])];

/** Paste and drop take every file; a plain text paste goes on into the focused field. */
function listenForFiles(dialog: HTMLElement, onFiles: (files: readonly File[]) => void): void {
  dialog.addEventListener("paste", (event) => {
    const files = listed(event.clipboardData?.files);
    if (files.length === 0) return;
    event.preventDefault();
    onFiles(files);
  });
  dialog.addEventListener("dragover", (event) => {
    event.preventDefault();
  });
  dialog.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = listed(event.dataTransfer?.files);
    if (files.length > 0) onFiles(files);
  });
}

/** A hidden file input and the icon button that opens it; `attrs` narrows it (the camera one). */
function picker(name: string, glyph: IconName, label: string, attributes: Record<string, string>, onFiles: (files: readonly File[]) => void): [HTMLButtonElement, HTMLInputElement] {
  const input = h("input", { attrs: { hidden: true, multiple: true, name, type: "file", ...attributes } });
  input.addEventListener("change", () => {
    onFiles(listed(input.files));
    input.value = "";
  });
  const button = iconButton(glyph, label, { "data-new-task": name === "files" ? "pick" : name }, () => { input.click(); });
  return [button, input];
}

export function buildForm(handlers: FormHandlers): Form {
  const on = { input: handlers.onInput };
  const repo = h("input", {
    attrs: { "aria-label": "Repo (owner/name)", autocomplete: "off", list: LIST_ID, name: "repo", spellcheck: "false", title: "Repo (owner/name)" },
    on,
  });
  const title = h("input", { attrs: { "aria-label": "Title", maxlength: MAX_TITLE, name: "title", title: "Title" }, on });
  const body = h("textarea", { attrs: { "aria-label": "Details", maxlength: MAX_BODY, name: "body", rows: 6, title: "Details" }, on: { input: () => { handlers.onGrow(); handlers.onInput(); } } });
  const [pick, files] = picker("files", "attach", "Attach files (or paste, or drop them here)", {}, handlers.onFiles);
  const [camera, shot] = picker("camera", "camera", "Take a photo", { accept: "image/*", capture: "environment" }, handlers.onFiles);
  camera.classList.add("nt-camera");
  const thumbs = h("ul", { attrs: { "aria-label": "Attachments" }, class: "nt-thumbs" });
  const submit = iconButton("check", "Create and start", { "data-new-task": "submit" }, handlers.onSubmit, "primary");
  const cancel = iconButton("close", "Close", { "data-new-task": "cancel" }, handlers.onClose);
  const slot = h("div", { class: "nt-slot" });
  const list = h("datalist", { attrs: { id: LIST_ID } });
  const dialog = h(
    "aside",
    { attrs: { "aria-label": "New task", "aria-modal": "true", role: "dialog", tabindex: -1 }, class: "nt-dialog", on: { keydown: handlers.onKey } },
    row("folder", repo),
    list,
    row("tag", title),
    row("log", body),
    h("div", { class: "nt-row" }, pick, files, camera, shot, thumbs),
    slot,
    h("div", { class: "nt-actions" }, cancel, submit),
  );
  listenForFiles(dialog, handlers.onFiles);
  const panel = h("div", { attrs: { hidden: true }, class: "nt-panel" }, h("div", { class: "nt-scrim", on: { click: handlers.onClose } }), dialog);
  return { body, camera, cancel, dialog, list, panel, pick, repo, slot, submit, thumbs, title };
}

/** Images as thumbnails, anything else as a file icon and its name; each with its remove button. */
export function renderThumbs(form: Form, files: readonly Attached[], onRemove: (index: number) => void): void {
  form.thumbs.replaceChildren(
    ...files.map(({ file, url }, index) => {
      const shown = url === null
        ? h("span", { attrs: { title: file.name }, class: "nt-file" }, icon("file"), h("span", { text: file.name }))
        : h("img", { attrs: { alt: file.name, src: url, title: file.name } });
      return h("li", {}, shown, iconButton("trash", `Remove ${file.name}`, { "data-new-task": "remove" }, () => { onRemove(index); }));
    }),
  );
}
