/** The paced free-credits object the server sends in `limit.credits` (week 2 of 4, a fifth of the grant spent). */
import type { Credits } from "@/lib/schemas-common";

export function makeCredits(over: Partial<Credits> = {}): Credits {
  return {
    cap_usd: 100,
    cost_factor: 0.47,
    credit_turns_period: 12,
    enabled: true,
    monthly_usd: 200,
    over_cap: false,
    period_start: 1_792_740_800,
    remaining_usd: 160,
    route: "credits",
    running_credit_turns: 1,
    spent_period_usd: 40,
    state: "ready",
    text: "Turns run on free API credits, paced by week (model claude-opus-5-5).",
    week: 2,
    ...over,
  };
}
