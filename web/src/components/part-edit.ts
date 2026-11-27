import type { RepoPart, TaskCard } from "@/lib/schemas-common";

/**
 * Edit a repo part's own title and text in the drawer before the run reaches it (856c0f0a). The server decides
 * which parts are editable (`parts[].edit`); a locked pencil carries its reason in aria-label and title. The
 * new title shows in the row on the click, the form locks while the server writes, a loader names the wait
 * after 1 s, and the server's answer is the truth. Icons only: titles and text are kuhy's own content.
 */
import { slowTimer } from "@/components/action-bar";
import { loader, showToast } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { csrfToken } from "@/lib/boot";
import { h, must } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { postPartEdit } from "@/lib/part-edit-api";

interface Draft {
  body: string;
  title: string;
}
interface View {
  card: TaskCard;
  root: HTMLElement;
}

const rowOf = (id: string): string => `[data-parts-detail] li[data-id="${CSS.escape(id)}"]`;
const titleName = (id: string): string => `part-title-${id}`;

export class PartEditor {
  #draft: Draft = { body: "", title: "" };
  readonly #done: (card: string) => Promise<void>;
  #open: null | string = null;
  #pending = false;
  #slow = false;
  #view!: View; // set by mount(), before any control it draws can call back

  /** `done` re-reads the task once a save landed; the editor then tells the board (task-changed). */
  constructor(done: (card: string) => Promise<void>) {
    this.#done = done;
  }

  #repaint(): void {
    this.mount(this.#view.root, this.#view.card);
  }

  #pencil(part: RepoPart, view: View): HTMLElement {
    const label = part.edit.enabled ? `Edit ${part.title}` : `Edit ${part.title}: ${part.edit.reason}`;
    const button = iconButton("edit", label, { "data-part-edit": part.id, disabled: !part.edit.enabled || this.#pending }, () => {
      this.#open = part.id;
      this.#draft = { body: part.body ?? "", title: part.title };
      this.#repaint();
      must<HTMLInputElement>(view.root, `[name="${titleName(part.id)}"]`).focus();
    });
    button.title = part.edit.enabled ? "Edit" : part.edit.reason;
    return h("span", { attrs: { "data-part-tools": "" }, class: "p-tools" }, button);
  }

  #form(part: RepoPart, view: View): HTMLElement {
    const keep = (key: keyof Draft): ((event: Event) => void) => {
      return (event: Event): void => {
        this.#draft = { ...this.#draft, [key]: (event.target as HTMLInputElement | HTMLTextAreaElement).value };
      };
    };
    const isLocked = this.#pending;
    const title = h("input", { attrs: { "aria-label": "Title", "data-keep": "", disabled: isLocked, maxlength: 200, name: titleName(part.id), type: "text", value: this.#draft.title }, class: "p-input", on: { input: keep("title") } });
    const body = h("textarea", { attrs: { "aria-label": "Text", "data-keep": "", disabled: isLocked, name: `part-body-${part.id}`, rows: 6 }, class: "p-input", on: { input: keep("body") } });
    body.value = this.#draft.body;
    const save = iconButton("check", "Save", { "aria-busy": isLocked, "data-part-save": part.id, disabled: isLocked }, () => {
      void this.#save(part, view, title, body);
    });
    const cancel = iconButton("close", "Cancel", { "data-part-cancel": part.id, disabled: isLocked }, () => {
      this.#open = null;
      this.#repaint();
    });
    const wait = isLocked && this.#slow && loader(`Saving part ${part.id} to its todo note…`);
    return h("div", { attrs: { "data-part-form": part.id, role: "group" }, class: "p-form" }, title, body, h("span", { class: "p-form-actions" }, save, cancel), wait);
  }

  async #save(part: RepoPart, view: View, titleBox: HTMLInputElement, bodyBox: HTMLTextAreaElement): Promise<void> {
    const csrf = csrfToken();
    const title = titleBox.value.trim();
    if (title === "") {
      titleBox.setAttribute("aria-invalid", "true");
      titleBox.focus();
      return;
    }
    if (csrf === null) {
      showToast("This page has no CSRF token (index.html was not stamped by the server). Reload it from the server.", "error");
      return;
    }
    this.#draft = { body: bodyBox.value, title: titleBox.value };
    this.#pending = true;
    const shown = must(view.root, `${rowOf(part.id)} .p-title`);
    shown.textContent = title; // the new title shows on the click, before the server answers
    this.#repaint();
    const stop = slowTimer(() => {
      this.#slow = true;
      this.#repaint();
    });
    try {
      await postPartEdit(view.card.id, part.id, title, bodyBox.value, csrf);
      this.#open = null;
      this.#pending = false;
      await this.#done(view.card.id);
      view.root.dispatchEvent(new CustomEvent("task-changed", { bubbles: true }));
    } catch (error) {
      shown.textContent = part.title;
      showToast(errorText(error), "error");
    } finally {
      stop();
      this.#pending = false;
      this.#slow = false;
      this.#repaint();
    }
  }

  /** Add a pencil to every row of the drawer's parts checklist and the open form; call after each head paint. */
  mount(root: HTMLElement, card: TaskCard): void {
    const view = { card, root };
    this.#view = view;
    if (card.parts === undefined) return;
    for (const part of card.parts) {
      const rows = root.querySelectorAll<HTMLElement>(rowOf(part.id));
      for (const row of rows) {
        for (const old of row.querySelectorAll("[data-part-tools], [data-part-form]")) old.remove();
        row.append(this.#pencil(part, view));
        if (this.#open === part.id && part.edit.enabled) row.append(this.#form(part, view));
      }
    }
  }

  reset(): void {
    this.#open = null;
    this.#pending = false;
    this.#slow = false;
  }
}
