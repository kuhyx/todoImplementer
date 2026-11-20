/**
 * The new-task dialog's first step: where the task goes. Chips for none, all (icons; names only in aria-label and
 * title) and each board repo (its name), several repos at once; a typed owner/name filters the chips, and Enter
 * picks the one match or adds a repo that is not on the board. Once picked the chooser folds to one row of the
 * picks; a click on that row opens it again. None and all are one repo-less note that triage routes (DOCS-triage.md).
 */
import { icon, iconButton } from "@/components/icons";
import { h } from "@/lib/dom";
import { REPO } from "@/lib/newtask-api";

export type Scope = "all" | "none" | "some";

const LIST_ID = "nt-repos";
const LABELS = { all: "All repos (one note, triage routes it)", none: "No repo (triage routes it)" } as const;
const GLYPHS = { all: "all", none: "circle" } as const;

export class RepoChooser {
  readonly #chips: HTMLElement;
  readonly #repoChips: HTMLElement;
  readonly #folded: HTMLButtonElement;
  readonly #list: HTMLDataListElement;
  readonly #onChange: (isFolded: boolean) => void;
  readonly #picked = new Set<string>();
  #repos: string[] = [];
  #scope: null | Scope = null;
  readonly #scopes: Record<"all" | "none", HTMLButtonElement>;
  #signature = "";
  readonly element: HTMLElement;
  readonly typed: HTMLInputElement;

  constructor(onChange: (isFolded: boolean) => void) {
    this.#onChange = onChange;
    this.typed = h("input", {
      attrs: { "aria-label": "Repo (owner/name)", autocomplete: "off", list: LIST_ID, name: "repo", spellcheck: "false", title: "Repo (owner/name)" },
      on: { input: () => { this.#filter(); }, keydown: (event) => { this.#onKey(event); } },
    });
    this.#scopes = { all: this.#scopeChip("all"), none: this.#scopeChip("none") };
    this.#list = h("datalist", { attrs: { id: LIST_ID } });
    this.#repoChips = h("div", { class: "nt-repo-chips" });
    this.#chips = h("div", { attrs: { "aria-label": "Repos", role: "group" }, class: "nt-chips" }, this.#scopes.none, this.#scopes.all, this.typed, this.#repoChips);
    this.#folded = h("button", { attrs: { "aria-expanded": "false", "data-new-task": "scope", hidden: true, type: "button" }, class: "nt-picked", on: { click: () => { this.#fold(false); } } });
    this.element = h("div", { class: "nt-chooser" }, this.#folded, this.#chips, this.#list);
  }

  #scopeChip(scope: "all" | "none"): HTMLButtonElement {
    const chip = iconButton(GLYPHS[scope], LABELS[scope], { "data-scope": scope }, () => { this.#pick(scope); });
    chip.classList.add("nt-chip");
    return chip;
  }

  #pick(scope: "all" | "none"): void {
    this.#picked.clear();
    this.#scope = scope;
    this.#fold(true);
  }

  #toggle(repo: string): void {
    if (this.#scope !== "some") this.#picked.clear();
    if (this.#picked.has(repo)) this.#picked.delete(repo);
    else this.#picked.add(repo);
    this.#scope = this.#picked.size > 0 ? "some" : null;
    this.typed.value = "";
    this.#filter();
    this.#fold(this.#scope !== null);
  }

  #fold(isFolded: boolean): void {
    this.#chips.hidden = isFolded;
    this.#folded.hidden = !isFolded;
    this.#paint();
    this.#onChange(isFolded);
  }

  #filter(): void {
    const text = this.typed.value.trim().toLowerCase();
    for (const chip of this.#repoChips.querySelectorAll<HTMLElement>("[data-repo]")) chip.hidden = !String(chip.dataset.repo).toLowerCase().includes(text);
  }

  #onKey(event: KeyboardEvent): void {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const shown = [...this.#repoChips.querySelectorAll<HTMLElement>("[data-repo]:not([hidden])")].map((chip) => String(chip.dataset.repo));
    const typed = this.typed.value.trim();
    const only = shown.length === 1 ? shown[0] : undefined;
    const repo = REPO.test(typed) ? typed : only;
    if (repo !== undefined) this.#toggle(repo);
  }

  #paint(): void {
    for (const scope of ["all", "none"] as const) this.#scopes[scope].setAttribute("aria-pressed", String(this.#scope === scope));
    const names = [...this.#repos];
    for (const repo of this.#picked) if (!names.includes(repo)) names.push(repo);
    const old = new Map([...this.#repoChips.querySelectorAll<HTMLButtonElement>("[data-repo]")].map((chip) => [chip.dataset.repo, chip]));
    const chips = names.map((repo) => old.get(repo) ?? h("button", { attrs: { "data-repo": repo, type: "button" }, class: "nt-chip", on: { click: () => { this.#toggle(repo); } }, text: repo }));
    for (const chip of chips) chip.setAttribute("aria-pressed", String(this.#picked.has(String(chip.dataset.repo))));
    this.#repoChips.replaceChildren(...chips);
    this.#filter();
    const scope = this.#scope;
    const label = scope === "all" || scope === "none" ? LABELS[scope] : [...this.#picked].join(", ");
    this.#folded.setAttribute("aria-label", `Repos: ${label}`);
    this.#folded.title = label;
    this.#folded.replaceChildren(...(scope === "all" || scope === "none" ? [icon(GLYPHS[scope])] : [...this.#picked].map((repo) => h("span", { class: "nt-chip", text: repo }))));
  }

  /** The repos still to send to; `[null]` is one repo-less note (none or all). */
  targets(): (null | string)[] {
    if (this.#scope === "some") return [...this.#picked];
    return this.#scope === null ? [] : [null];
  }

  /** A repo whose task is made: a retry after a later refusal does not send it twice. */
  sent(repo: null | string): void {
    if (repo !== null) this.#picked.delete(repo);
    this.#paint();
  }

  /** Starts over: on the board's repo filter (folded) when there is one, else open with nothing picked. */
  reset(repo: string): void {
    this.#picked.clear();
    if (repo !== "") this.#picked.add(repo);
    this.#scope = repo === "" ? null : "some";
    this.typed.value = "";
    this.#filter();
    this.#fold(repo !== "");
  }

  set repos(list: readonly string[]) {
    const signature = list.join("\n");
    if (signature === this.#signature) return;
    this.#signature = signature;
    this.#repos = [...list];
    this.#list.replaceChildren(...list.map((repo) => h("option", { attrs: { value: repo } })));
    this.#paint();
  }

  get scope(): null | Scope {
    return this.#scope;
  }
}
