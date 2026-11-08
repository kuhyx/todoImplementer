/** Values the server stamps into index.html; an unreplaced `__PLACEHOLDER__` counts as missing. */
export function readMeta(name: string): null | string {
  const content = document.querySelector(`meta[name="${CSS.escape(name)}"]`)?.getAttribute("content") ?? "";
  return content === "" || content.startsWith("__") ? null : content;
}

export const csrfToken = (): null | string => readMeta("todoimpl-csrf");
export const pageBuild = (): null | string => readMeta("todoimpl-build");

export interface InputSnapshot {
  focus: null | string;
  values: Map<string, string>;
}

type KeptField = HTMLInputElement | HTMLTextAreaElement;
const isBox = (field: KeptField): field is HTMLInputElement => field instanceof HTMLInputElement && field.type === "checkbox";

export function snapshotInputs(root: ParentNode): InputSnapshot {
  const values = new Map<string, string>();
  for (const field of root.querySelectorAll<KeptField>("[data-keep]")) {
    values.set(field.name, isBox(field) ? String(field.checked) : field.value);
  }
  const active = document.activeElement;
  const isField = active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement;
  const focus = isField && root.contains(active) && active.dataset.keep !== undefined ? active.name : null;
  return { focus, values };
}

export function restoreInputs(root: ParentNode, snapshot: InputSnapshot): void {
  for (const field of root.querySelectorAll<KeptField>("[data-keep]")) {
    const kept = snapshot.values.get(field.name);
    if (kept !== undefined && isBox(field)) field.checked = kept === "true";
    else if (kept !== undefined) field.value = kept;
    if (snapshot.focus === field.name) field.focus();
  }
}
