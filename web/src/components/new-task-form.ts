/** The new-task dialog's DOM: icon-labelled fields (names in aria-label and title, no visible words), thumbnails, actions. */
import { icon, iconButton, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { MAX_BODY, MAX_TITLE } from "@/lib/newtask-api";

export interface FormHandlers {
  onClose: () => void;
  onFiles: (files: readonly File[]) => void;
  onInput: () => void;
  onKey: (event: KeyboardEvent) => void;
  onPick: () => void;
  onSubmit: () => void;
}

export interface Form {
  body: HTMLTextAreaElement;
  cancel: HTMLButtonElement;
  dialog: HTMLElement;
  list: HTMLDataListElement;
  panel: HTMLElement;
  pick: HTMLButtonElement;
  picker: HTMLInputElement;
  repo: HTMLInputElement;
  slot: HTMLElement;
  submit: HTMLButtonElement;
  thumbs: HTMLElement;
  title: HTMLInputElement;
}

const LIST_ID = "nt-repos";

function row(glyph: IconName, control: HTMLElement): HTMLElement {
  return h("div", { class: "nt-row" }, h("span", { attrs: { "aria-hidden": "true" }, class: "nt-glyph" }, icon(glyph)), control);
}

const imageFiles = (files: FileList | null | readonly File[] | undefined): File[] =>
  [...(files ?? [])].filter((file) => file.type.startsWith("image/"));

/** Paste and drop take image files only; a plain text paste goes on into the focused field. */
function listenForFiles(dialog: HTMLElement, onFiles: (files: readonly File[]) => void): void {
  dialog.addEventListener("paste", (event) => {
    const files = imageFiles(event.clipboardData?.files);
    if (files.length === 0) return;
    event.preventDefault();
    onFiles(files);
  });
  dialog.addEventListener("dragover", (event) => {
    event.preventDefault();
  });
  dialog.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = imageFiles(event.dataTransfer?.files);
    if (files.length > 0) onFiles(files);
  });
}

export function buildForm(handlers: FormHandlers): Form {
  const on = { input: handlers.onInput };
  const repo = h("input", {
    attrs: { "aria-label": "Repo (owner/name)", autocomplete: "off", list: LIST_ID, name: "repo", spellcheck: "false", title: "Repo (owner/name)" },
    on,
  });
  const title = h("input", { attrs: { "aria-label": "Title", maxlength: MAX_TITLE, name: "title", title: "Title" }, on });
  const body = h("textarea", { attrs: { "aria-label": "Details", maxlength: MAX_BODY, name: "body", rows: 6, title: "Details" }, on });
  const picker = h("input", { attrs: { accept: "image/*", hidden: true, multiple: true, name: "images", type: "file" } });
  picker.addEventListener("change", () => {
    handlers.onFiles(imageFiles(picker.files));
    picker.value = "";
  });
  const pick = iconButton("photo", "Add pictures (or paste, or drop them here)", { "data-new-task": "pick" }, handlers.onPick);
  const thumbs = h("ul", { attrs: { "aria-label": "Pictures" }, class: "nt-thumbs" });
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
    h("div", { class: "nt-row" }, pick, picker, thumbs),
    slot,
    h("div", { class: "nt-actions" }, cancel, submit),
  );
  listenForFiles(dialog, handlers.onFiles);
  const panel = h("div", { attrs: { hidden: true }, class: "nt-panel" }, h("div", { class: "nt-scrim", on: { click: handlers.onClose } }), dialog);
  return { body, cancel, dialog, list, panel, pick, picker, repo, slot, submit, thumbs, title };
}

export function renderThumbs(form: Form, images: readonly string[], onRemove: (index: number) => void): void {
  form.thumbs.replaceChildren(
    ...images.map((data, index) => {
      return h(
        "li",
        {},
        h("img", { attrs: { alt: "", src: `data:image/jpeg;base64,${data}` } }),
        iconButton("trash", "Remove picture", { "data-new-task": "remove" }, () => {
          onRemove(index);
        }),
      );
    },
    ),
  );
}
