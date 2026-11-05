import type { Action } from "@/lib/schemas-common";

import { type BarState, idleBar, renderAction, slowTimer } from "@/components/action-bar";
/** Side drawer for one task: live feed, plan, diff, live check, check output, spec questions, actions and the Send-to-Claude box. */
import { AskPanel } from "@/components/ask-view";
import { paintDetail } from "@/components/drawer-render";
import { buildShell, paintTabs, type Tab, trapTab } from "@/components/drawer-shell";
import { createFeed } from "@/components/feed-view";
import { loader, showToast } from "@/components/feedback";
import { csrfToken, restoreInputs, snapshotInputs } from "@/lib/boot";
import { h, must } from "@/lib/dom";
import { errorText, getJson, postAction } from "@/lib/http";
import { openLive } from "@/lib/live-feed";
import { poll } from "@/lib/poller";
import { routes } from "@/lib/routes";
import { type LiveEvent, type TaskDetail, taskDetail } from "@/lib/schemas";

const DETAIL_POLL_MS = 5000;

export class TiDrawer extends HTMLElement {
  readonly #ask = new AskPanel();
  #bar: BarState = idleBar();
  #detail: null | TaskDetail = null;
  #feed = createFeed();
  #id: null | string = null;
  #opener: HTMLElement | null = null;
  #signature = "";
  #stops: (() => void)[] = [];
  #tab: Tab = "activity";

  #buildShell(): void {
    this.replaceChildren(
      ...buildShell(this.#feed.el, {
        onClose: () => {
          this.close();
        },
        onKey: (event) => {
          this.#onKey(event);
        },
        onSend: () => {
          this.querySelector<HTMLButtonElement>('[data-action="send"]')?.click();
        },
      }),
    );
    this.#paintTabs();
  }

  #paintTabs(): void {
    paintTabs(this, this.#detail, this.#tab, (tab) => {
      this.#tab = tab;
      this.#paintTabs();
    });
    this.#ask.fit();
  }

  async #refresh(id: string): Promise<void> {
    try {
      const detail = await getJson(routes.task(id), taskDetail);
      if (this.#id === id) {
        this.#detail = detail;
        this.#render();
      }
    } catch (error) {
      if (this.#id !== id) return;
      must(this, '[data-slot="head"]').replaceChildren(h("p", { attrs: { role: "alert" }, class: "banner", text: `Cannot load task ${id}: ${errorText(error)}` }));
    }
  }

  #onLive(event: LiveEvent): void {
    if (event.type === "activity") {
      this.#feed.append(event);
      return;
    }
    const detail = this.#detail;
    if (detail !== null && event.type === "stage") {
      const { actions, column, current, needs, stage, status } = event;
      this.#detail = { ...detail, card: { ...detail.card, actions, column, current, needs, stage, status } };
      this.#render();
    }
    if (detail !== null && event.type === "cost") {
      this.#detail = { ...detail, card: { ...detail.card, cost_usd: event.cost_usd } };
      this.#render();
    }
    if (event.type === "cost" || this.#id === null) {
      return;
    }

    void this.#refresh(this.#id);
    this.dispatchEvent(new CustomEvent("task-changed", { bubbles: true }));
  }

  #render(): void {
    const detail = this.#detail;
    if (detail === null) return;
    this.#tab = this.#ask.tabFor(detail, this.#tab);
    const signature = JSON.stringify([detail, this.#bar, this.#tab]);
    if (signature === this.#signature) return;
    this.#signature = signature;
    const snapshot = snapshotInputs(this);
    paintDetail(this, detail, this.#host(detail), this.#bar, this.#ask);
    this.#paintTabs();
    restoreInputs(this, snapshot);
  }

  #cancelConfirm(): void {
    this.#bar = { ...this.#bar, confirming: null };
    this.#render();
  }

  #host(detail: TaskDetail): Parameters<typeof renderAction>[1] {
    return {
      activate: (action) => {
        void this.#activate(detail, action);
      },
      cancelConfirm: () => {
        this.#cancelConfirm();
      },
      state: () => this.#bar,
    };
  }

  async #activate(detail: TaskDetail, action: Action): Promise<void> {
    if (action.confirm === true && this.#bar.confirming !== action.id) {
      this.#bar = { ...this.#bar, confirming: action.id };
      this.#render();
      this.querySelector<HTMLElement>("[data-confirm]")?.focus();
      return;
    }
    if (action.id === "copy-resume") {
      const text = action.value ?? detail.resume_command;
      if (text === null) showToast("There is no resume command yet.", "error");
      else await this.#copy(text);
      return;
    }
    await this.#post(detail, action);
  }

  async #copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      showToast("Resume command copied");
    } catch {
      showToast(`Copy was blocked here. Command: ${text}`, "error");
    }
  }

  async #post(detail: TaskDetail, action: Action): Promise<void> {
    const csrf = csrfToken();
    if (csrf === null) {
      showToast("This page has no CSRF token (index.html was not stamped by the server). Reload it from the server.", "error");
      return;
    }
    const sendBox = this.querySelector<HTMLTextAreaElement>("textarea[name=ask-send]") ?? must<HTMLTextAreaElement>(this, "textarea[name=send]");
    const answers = this.#ask.answers();
    const text = sendBox.value.trim();
    if (text === "" && action.id === "send") {
      showToast("Write a message first.", "error");
      return;
    }
    if (Object.keys(answers).length === 0 && action.id === "spec-answers") {
      showToast("Write at least one answer first.", "error");
      return;
    }
    this.#bar = { confirming: null, pending: action.id, slow: false };
    this.#render();
    const stop = slowTimer(() => {
      this.#bar = { ...this.#bar, slow: true };
      this.#render();
    });
    try {
      await postAction(detail.card.id, action.id, { answers, lessonId: detail.lesson?.id ?? "", text }, csrf);
      if (action.id === "send") for (const box of this.querySelectorAll<HTMLTextAreaElement>("textarea[name$=send]")) box.value = "";
      showToast(`${action.label}: done`);
    } catch (error) {
      showToast(errorText(error), "error");
    } finally {
      stop();
      this.#bar = idleBar();
      if (this.#id !== null) await this.#refresh(this.#id);
      this.dispatchEvent(new CustomEvent("task-changed", { bubbles: true }));
    }
  }

  #onKey(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (this.#bar.confirming === null) this.close();
      else this.#cancelConfirm();
      return;
    }
    if (event.key === "Tab") trapTab(event, this);
  }

  open(id: string, opener: HTMLElement | null = null): void {
    this.close(false);
    this.#id = id;
    this.#opener = opener;
    this.#detail = null;
    this.#signature = "";
    this.#ask.reset();
    this.#bar = idleBar();
    this.#feed = createFeed();
    this.hidden = false;
    this.#buildShell();
    must(this, '[data-slot="head"]').append(loader(`Loading task ${id} from ${routes.task(id)}…`));
    this.querySelector<HTMLElement>(".drawer")?.focus();
    this.#stops = [
      poll(() => this.#refresh(id), DETAIL_POLL_MS),
      openLive(id, {
        onBad: (message) => {
          showToast(message, "error");
        },
        onEvent: (event) => {
          this.#onLive(event);
        },
        onState: (state) => {
          this.#feed.setState(state);
        },
      }),
    ];
  }

  close(shouldNotify = true): void {
    for (const stop of this.#stops) stop();
    this.#stops = [];
    const opener = this.#opener;
    this.#id = null;
    this.#detail = null;
    this.#opener = null;
    this.hidden = true;
    this.replaceChildren();
    if (!shouldNotify) {
      return;
    }

    this.dispatchEvent(new CustomEvent("drawer-close", { bubbles: true }));
    if (opener?.isConnected === true) opener.focus();
  }
}

export function defineDrawer(): void {
  if (!customElements.get("ti-drawer")) customElements.define("ti-drawer", TiDrawer);
}
