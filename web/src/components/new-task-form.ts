/** The new-task dialog's DOM: the repo chooser, one description box (its first line is the title), then one row with attach, camera, the attachments, close and OK. Icons only; names in aria-label and title. */
import { icon, iconButton, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { MAX_BODY } from "@/lib/newtask-api";

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
  panel: HTMLElement;
  pick: HTMLButtonElement;
  slot: HTMLElement;
  submit: HTMLButtonElement;
  thumbs: HTMLElement;
}

/** One file in the dialog: `url` is its object URL when it is an image (a thumbnail), `id` once uploaded. */
export interface Attached {
  file: File;
  id?: string;
  /** A numbered image: `[Image #N]` in the details, posted as `images` (T2321); else a plain file. */
  image: boolean;
  url: null | string;
}

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

/** `chooser` is the first step (the repo chooser's element); the description box follows it. */
export function buildForm(handlers: FormHandlers, chooser: HTMLElement): Form {
  const body = h("textarea", {
    attrs: { "aria-label": "Description (first line is the title)", maxlength: MAX_BODY, name: "body", rows: 18, title: "Description (first line is the title)" },
    on: { input: () => { handlers.onGrow(); handlers.onInput(); } },
  });
  const [pick, files] = picker("files", "attach", "Attach files (or paste, or drop them here)", {}, handlers.onFiles);
  const [camera, shot] = picker("camera", "camera", "Take a photo", { accept: "image/*", capture: "environment" }, handlers.onFiles);
  camera.classList.add("nt-camera");
  const thumbs = h("ul", { attrs: { "aria-label": "Attachments" }, class: "nt-thumbs" });
  const submit = iconButton("check", "Create and start", { "data-new-task": "submit" }, handlers.onSubmit, "primary");
  const cancel = iconButton("close", "Close", { "data-new-task": "cancel" }, handlers.onClose);
  const slot = h("div", { class: "nt-slot" });
  const dialog = h(
    "aside",
    { attrs: { "aria-label": "New task", "aria-modal": "true", role: "dialog", tabindex: -1 }, class: "nt-dialog", on: { keydown: handlers.onKey } },
    row("folder", chooser),
    row("log", body),
    slot,
    h("div", { class: "nt-bar" }, pick, files, camera, shot, thumbs, h("div", { class: "nt-actions" }, cancel, submit)),
  );
  listenForFiles(dialog, handlers.onFiles);
  const panel = h("div", { attrs: { hidden: true }, class: "nt-panel" }, h("div", { class: "nt-scrim", on: { click: handlers.onClose } }), dialog);
  return { body, camera, cancel, dialog, panel, pick, slot, submit, thumbs };
}

/** Images as thumbnails, anything else as a file icon and its name; each with its remove button. */
export function renderThumbs(form: Form, files: readonly Attached[], onRemove: (index: number) => void): void {
  let number = 0;
  form.thumbs.replaceChildren(
    ...files.map(({ file, image, url }, index) => {
      const shown = url === null
        ? h("span", { attrs: { title: file.name }, class: "nt-file" }, icon("file"), h("span", { text: file.name }))
        : h("img", { attrs: { alt: file.name, src: url, title: file.name } });
      if (image) number += 1;
      const label = image && h("span", { class: "chip-n", text: `#${String(number)}` });
      return h("li", {}, shown, label, iconButton("trash", `Remove ${file.name}`, { "data-new-task": "remove" }, () => { onRemove(index); }));
    }),
  );
}
