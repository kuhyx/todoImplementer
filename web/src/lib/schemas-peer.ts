/** Zod mirror of contracts/peer.schema.json $defs/message and thread (a task's Peer thread, DOCS-peer.md). */
import { z } from "zod";

import { epoch } from "@/lib/schemas-common";

export const PEER_STATES = ["queued", "delivered", "answered", "expired", "dead_end"] as const;
const messageId = z.string().regex(/^[A-Za-z\d]{8}-\d+\.[\da-f]{12}$/v);
const senderId = z.string().regex(/^[\da-f]{4}$/v);

export const peerMessage = z.strictObject({
  answered_at: epoch.nullable(),
  at: epoch,
  card: z.string(),
  delivered_at: epoch.nullable(),
  from: z.string(),
  from_id: senderId,
  hop: z.number().int().min(1).max(7),
  id: messageId,
  reason: z.string().nullable(),
  reply: z.string().nullable(),
  reply_to: messageId.nullable(),
  state: z.enum(PEER_STATES),
  text: z.string().max(8192),
  to: z.string(),
  to_card: z.string().nullable(),
  to_id: senderId,
});
export const peerThread = z.array(peerMessage).max(50);

export type PeerMessage = z.infer<typeof peerMessage>;
