import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  collectAnswers, renderChecks, renderDetails, renderDiff, renderHead, renderLesson, renderLiveCheck, renderNeeds,
  renderPlan, renderQuestions,
} from "@/components/drawer-sections";
import { renderMarkdown } from "@/lib/markdown";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards, NOW } from "@/test/fixtures";

afterEach(() => {
  document.body.replaceChildren();
});

beforeEach(() => {
  document.body.replaceChildren();
});

const byStatus = (status: string) => {
  const card = makeCards().find((c) => c.status === status);
  if (card === undefined) throw new Error(status);
  return card;
};
const act = (): ((id: string) => null) => () => null;

describe("drawer sections", () => {
  it("head shows chips, title and current line; Yours has no repo", () => {
    const head = renderHead(makeDetail(byStatus("working")));
    expect(head.querySelector("h2")?.textContent).toBe("Escape hatch needs keyboard path");
    expect(head.textContent).toContain("gatelock");
    const yours = renderHead(makeDetail(byStatus("yours")));
    expect(yours.textContent).toContain("Yours (no repo)");
  });

  it("needs banner names the need; an error shows alone or beside it", () => {
    const needy = makeDetail(byStatus("needs_you"));
    expect(renderNeeds(needy)?.textContent).toContain("Answer 2 questions so Claude can plan.");
    expect(renderNeeds({ ...needy, error: "push refused" })?.textContent).toContain("push refused");
    const calm = makeDetail(byStatus("working"));
    expect(renderNeeds(calm)).toBeNull();
    expect(renderNeeds({ ...calm, error: "boom" })?.getAttribute("role")).toBe("alert");
  });

  it("spec questions prefill the recommendation, keep a given answer, and collect answers", () => {
    const detail = makeDetail(byStatus("needs_you"));
    const slot = vi.fn((id: string) => (id === "spec-answers" ? document.createElement("i") : null));
    const element = renderQuestions(detail, slot);
    if (element === null) throw new Error("questions");
    document.body.append(element);
    const [q1, q2] = element.querySelectorAll<HTMLTextAreaElement>("textarea");
    expect([q1?.value, q2?.value]).toEqual(["localStorage", "Yes"]);
    expect(element.textContent).toContain("Recommended: localStorage");
    expect(element.querySelector("i")).not.toBeNull();
    if (q1 === undefined) throw new Error("q1");
    q1.value = "sessionStorage";
    element.querySelector<HTMLElement>(".qcard .btn")?.click();
    expect(q1.value).toBe("localStorage");
    q1.value = "  ";
    expect(collectAnswers(element)).toEqual({ Q2: "Yes" });
    expect(renderQuestions(makeDetail(byStatus("working")), act())).toBeNull();
    expect(renderQuestions({ ...detail, questions: [{ ...detail.questions[0]!, body: "" }] }, act())?.querySelectorAll(".qcard p")).toHaveLength(1);
  });

  it("lesson block shows the draft and its action", () => {
    const detail = makeDetail(byStatus("ready_to_ship"));
    const element = renderLesson(detail, () => document.createElement("b"));
    expect(element?.textContent).toContain("Skipped the red test");
    expect(element?.querySelector("b")).not.toBeNull();
    expect(renderLesson(makeDetail(byStatus("working")), act())).toBeNull();
  });

  it("plan renders markdown or says why there is none", () => {
    expect(renderPlan(makeDetail(byStatus("working"))).querySelector("h3")?.textContent).toBe("Plan");
    expect(renderPlan(makeDetail(byStatus("backlog"))).textContent).toContain("No plan yet");
  });

  it("diff shows files, coloured lines and truncation", () => {
    const detail = makeDetail(byStatus("working"));
    const element = renderDiff(detail);
    expect([...element.querySelectorAll(".diff-line")].map((l) => l.getAttribute("data-kind"))).toEqual(["meta", "meta", "meta", "meta", "hunk", "ctx", "del", "add", "add", "ctx"]);
    expect(element.textContent).toContain("+2");
    expect(element.textContent).not.toContain("cut off");
    const big = renderDiff({ ...detail, diff: { ...detail.diff!, patch: "+x\n".repeat(6000), truncated: false } });
    expect(big.querySelectorAll(".diff-line")).toHaveLength(5000);
    expect(big.textContent).toContain("cut off");
    expect(renderDiff({ ...detail, diff: { ...detail.diff!, truncated: true } }).textContent).toContain("cut off");
    expect(renderDiff({ ...detail, diff: null }).textContent).toContain("No changes yet");
  });

  it("checks show each command's exit and output tail", () => {
    const element = renderChecks(makeDetail(byStatus("working")));
    expect(element.textContent).toContain("make check");
    expect(element.textContent).toContain("42 passed in 3.1 s");
    expect(element.querySelector(".chip")?.textContent).toBe("Failed");
    expect(element.querySelectorAll(".chip")[2]?.textContent).toBe("exit 1");
    const green = makeDetail(byStatus("working"));
    expect(renderChecks({ ...green, checks: { ...green.checks!, passed: true } }).querySelector(".chip")?.textContent).toBe("All passed");
    expect(renderChecks(makeDetail(byStatus("backlog"))).textContent).toContain("No check output yet");
  });

  it("live check renders the report safely, the screenshots from the server and the self-check", () => {
    const detail = makeDetail(byStatus("working"));
    const element = renderLiveCheck(detail);
    expect(element.querySelector("h4")?.textContent).toBe("Live check");
    expect(element.textContent).toContain("Ship");
    const images = [...element.querySelectorAll("img")];
    expect(images.map((index) => index.getAttribute("src"))).toEqual([`/api/task/${detail.card.id}/shot/board.png`, `/api/task/${detail.card.id}/shot/drawer.png`]);
    expect(element.querySelector("a")?.getAttribute("target")).toBe("_blank");
    expect(element.textContent).toContain("not proof");
    expect(element.textContent).toContain("Page updates within 100 ms");
    expect(element.textContent).toContain("(42 passed)");
    const hostile = renderLiveCheck({ ...detail, live_check: { report_md: "<img src=x onerror=alert(1)> <script>x</script>", shots: [] }, self_check: [] });
    expect(hostile.querySelector("script")).toBeNull();
    expect(hostile.querySelectorAll("img")).toHaveLength(0);
    expect(hostile.textContent).toContain("No screenshots with this report.");
    const none = renderLiveCheck({ ...detail, live_check: null, self_check: [] });
    expect(none.textContent).toContain("No live check yet");
    expect(renderLiveCheck({ ...detail, live_check: null }).textContent).toContain("not proof");
  });

  it("details list only what exists", () => {
    const full = renderDetails(makeDetail(byStatus("working"))).textContent;
    for (const word of ["make check", "build-web-ui, safe-design-rules", "todoimpl/17a1b2c3-0", "claude --resume", "(running)"]) expect(full).toContain(word);
    const bare = renderDetails(makeDetail(byStatus("backlog"))).textContent;
    expect(bare).not.toContain("Worktree");
    expect(bare).toContain("Note");
    const done = makeDetail(byStatus("working"));
    expect(renderDetails({ ...done, stages: [{ ended: NOW, stage: "plan", started: NOW - 5 }] }).textContent).toContain(" to ");
  });
});

describe("markdown", () => {
  it("renders headings, lists, checkboxes, code and inline code", () => {
    const element = renderMarkdown("# H1\n## H2\n#### not\n- [ ] open `x`\n- [x] done\n- plain\n1. one\n\n```\ncode <b>\n```\ntext `a` b\nunterminated\n```\nopen");
    expect(element.querySelectorAll("h3, h4")).toHaveLength(2);
    expect(element.querySelectorAll("ul li")).toHaveLength(3);
    expect(element.querySelectorAll("ol li")).toHaveLength(1);
    expect(element.querySelector(".md-check.done")?.textContent).toBe("done");
    expect(element.querySelector("pre")?.textContent).toBe("code <b>");
    expect(element.querySelector("pre b")).toBeNull();
    expect(element.querySelectorAll("pre")).toHaveLength(2);
    expect(element.textContent).toContain("#### not");
  });

  it("starts a new list when the kind changes", () => {
    expect(renderMarkdown("- a\n1. b\n- c").querySelectorAll("ul, ol")).toHaveLength(3);
  });
});
