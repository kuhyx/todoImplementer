import type { LiveEvent, TaskDetail } from "@/lib/schemas";
import type { PeerMessage } from "@/lib/schemas-peer";

/**
 * What a live event changes in the open task's detail, merged at once with no refetch: the stage line, the cost,
 * or one Peer thread row (T2473: replaced by id or added, the thread keeps its last 50). Null: nothing to merge.
 */
const KEEP = 50;

function mergePeer(thread: PeerMessage[], message: PeerMessage): PeerMessage[] {
  const isKnown = thread.some((row) => row.id === message.id);
  return isKnown ? thread.map((row) => (row.id === message.id ? message : row)) : [...thread, message].slice(-KEEP);
}

export function mergeLive(detail: TaskDetail, event: LiveEvent): null | TaskDetail {
  if (event.type === "stage") {
    const { actions, column, current, needs, stage, status } = event;
    return { ...detail, card: { ...detail.card, actions, column, current, needs, stage, status } };
  }
  if (event.type === "cost") return { ...detail, card: { ...detail.card, cost_usd: event.cost_usd } };
  return event.type === "peer" ? { ...detail, peer: mergePeer(detail.peer ?? [], event.message) } : null;
}
