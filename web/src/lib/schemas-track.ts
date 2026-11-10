/** Zod mirror of contracts/track.schema.json (GET /api/umbrella/<id>): the tracking view of an umbrella run. */
import { z } from "zod";

import { epoch, itemId, stage, status, umbrellaCounts } from "@/lib/schemas-common";
import { VERDICTS } from "@/lib/schemas-umbrella";

export const RESTING_KINDS = ["limit", "network", "gateway", "killed", "crash", "todo", "turn"] as const;

export const resting = z
  .strictObject({
    kind: z.enum(RESTING_KINDS),
    until: epoch.nullable(),
  })
  .nullable();

const issue = z.strictObject({
  model: z.string().nullable(),
  phase: z.string(),
  symptom: z.string(),
  ts: epoch.nullable(),
});

const kid = z.strictObject({
  attempts: z.number().int().min(0),
  elapsed: z.number().min(0).nullable(),
  error: z.string().nullable(),
  free: z.boolean().nullable(),
  id: itemId,
  issues: z.number().int().min(0),
  killed: z.number().int().min(0),
  last_issue: issue.nullable(),
  log: z.boolean(),
  repo: z.string(),
  resting,
  round: z.number().int().nullable(),
  stage: stage.nullable(),
  status,
  title: z.string(),
  verdict: z.enum(VERDICTS).nullable(),
});

const round = z.strictObject({
  children: z.array(
    z.strictObject({
      checks: z.boolean().nullable(),
      detail: z.string(),
      free: z.boolean(),
      id: z.string(),
      ok: z.boolean(),
      repo: z.string(),
      verdict: z.enum(VERDICTS),
    }),
  ),
  ended: epoch.nullable(),
  n: z.number().int().min(1),
  next: z.number().int().min(1),
  started: epoch.nullable(),
  width: z.number().int().min(1),
});

const group = z.strictObject({
  count: z.number().int().min(1),
  fixed: z.number().int().min(0),
  lines: z.array(z.string()),
  model: z.string().nullable(),
  phase: z.string(),
});

export const track = z.strictObject({
  at: epoch,
  counts: umbrellaCounts,
  eta: z.strictObject({
    done: z.number().int().min(0),
    left: z.number().int().min(0),
    median: z.number().min(0).nullable(),
    seconds: z.number().min(0).nullable(),
    width: z.number().int().min(1),
  }),
  id: itemId,
  issues: z.strictObject({ groups: z.array(group), total: z.number().int().min(0) }),
  kids: z.array(kid),
  needs: z.number().int().min(0),
  resting,
  round: z
    .strictObject({
      ids: z.array(z.string()),
      n: z.number().int().min(1),
      started: epoch.nullable(),
      step: z.enum(["manager", "checks", "verdict"]),
      width: z.number().int().min(1),
    })
    .nullable(),
  rounds: z.array(round),
  stage,
  status,
  title: z.string(),
});

export type Track = z.infer<typeof track>;
export type TrackKid = Track["kids"][number];
export type TrackRound = Track["rounds"][number];
export type TrackGroup = Track["issues"]["groups"][number];
export type Resting = NonNullable<z.infer<typeof resting>>;
