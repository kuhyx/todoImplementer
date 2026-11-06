/** Drawer I/O: the question flow's one request (all spec answers in a single POST, which starts the spec turn at once, or one reply) and the clipboard. */
import { showToast } from "@/components/feedback";
import { csrfToken } from "@/lib/boot";
import { postAction } from "@/lib/http";

function token(): string {
  const csrf = csrfToken();
  if (csrf === null) throw new Error("This page has no CSRF token (index.html was not stamped by the server). Reload it from the server.");
  return csrf;
}

export async function postAnswers(cardId: string, answers: Record<string, string>): Promise<void> {
  await postAction(cardId, "spec-answers", { answers }, token());
}

/** A plain Claude question is answered with the card's send action: one message instead of spec answers. */
export async function postReply(cardId: string, text: string): Promise<void> {
  await postAction(cardId, "send", { lessonId: "", text }, token());
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    showToast("Command copied");
  } catch {
    showToast(`Copy was blocked here. Command: ${text}`, "error");
  }
}
