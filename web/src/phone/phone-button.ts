/** Icon-only button for the phone tools. Own class: the usage page does not load base.css. Name lives in aria-label and title (textgate). */
import { type IconName, setIcon } from "@/components/icons";
import { h } from "@/lib/dom";

export function phoneButton(name: IconName, label: string, kind: string, click: () => void): HTMLButtonElement {
  const button = h("button", { attrs: { "data-phone": kind, type: "button" }, class: "phone-btn", on: { click } });
  setIcon(button, name, label);
  return button;
}
