/**
 * The Send to Claude box and its images (T2320): a paste or the picker adds png/jpeg/webp/gif files (10 MB each,
 * 8 per message) as #N chips and puts `[Image #N]` at the caret; a refused file toasts why. Send uploads each
 * one once (POST /api/upload) and the send POST carries `images: [{upload}]`; a removed chip drops its tag and
 * renumbers the rest. The chips stay until a send succeeds, so a retry uploads nothing twice.
 */
import { showToast } from "@/components/feedback";
import { iconButton } from "@/components/icons";
import { h } from "@/lib/dom";
import { dropTag, IMAGE_TYPES, imageProblem, insertTag } from "@/lib/image-tags";
import { uploadFile } from "@/lib/newtask-api";

interface Item {
  file: File;
  id?: string;
  url: string;
}

export class SendImages {
  readonly #list = h("ul", { attrs: { "aria-label": "Images" }, class: "send-images nt-thumbs" });
  #items: Item[] = [];
  readonly box: HTMLTextAreaElement;
  readonly nodes: HTMLElement[];

  constructor() {
    this.box = h("textarea", {
      attrs: { "aria-label": "Message to Claude", "data-keep": true, name: "send", placeholder: "Send to Claude: a note, an answer or a correction", rows: 2 },
      on: {
        paste: (event) => {
          const files = [...(event.clipboardData?.files ?? [])];
          if (files.length === 0) return;
          event.preventDefault();
          this.add(files);
        },
      },
    });
    const input = h("input", { attrs: { accept: IMAGE_TYPES.join(","), hidden: true, multiple: true, name: "send-images", type: "file" } });
    input.addEventListener("change", () => {
      this.add([...(input.files ?? [])]);
      input.value = "";
    });
    const pick = iconButton("attach", "Attach images (or paste them)", { "data-send-images": "pick" }, () => { input.click(); });
    this.nodes = [pick, input, this.#list];
  }

  #remove(index: number): void {
    for (const { url } of this.#items.splice(index, 1)) URL.revokeObjectURL(url);
    this.box.value = dropTag(this.box.value, index + 1);
    this.#paint();
  }

  #paint(): void {
    this.#list.replaceChildren(
      ...this.#items.map(({ file, url }, index) => {
        return h(
          "li",
          {},
          h("img", { attrs: { alt: file.name, src: url, title: file.name } }),
          h("span", { class: "chip-n", text: `#${String(index + 1)}` }),
          iconButton("trash", `Remove image #${String(index + 1)}`, { "data-send-images": "remove" }, () => { this.#remove(index); }),
        );
      }),
    );
  }

  add(files: readonly File[]): void {
    for (const file of files) {
      const why = imageProblem(file, this.#items.length);
      if (why === null) {
        this.#items.push({ file, url: URL.createObjectURL(file) });
        insertTag(this.box, this.#items.length);
      } else showToast(why, "error");
    }
    this.#paint();
  }

  /** Uploads what is not uploaded yet; answers the refs in chip order. */
  async upload(csrf: string): Promise<{ upload: string }[]> {
    for (const item of this.#items) item.id ??= await uploadFile(item.file, csrf);
    return this.#items.map(({ id = "" }) => ({ upload: id }));
  }

  /** After a successful send: no chips, no object URLs. */
  clear(): void {
    for (const { url } of this.#items) URL.revokeObjectURL(url);
    this.#items = [];
    this.#paint();
  }
}
