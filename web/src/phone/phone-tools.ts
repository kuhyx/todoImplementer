/** Header buttons for phones: pair one (PC only, shown when the server stamped `todoimpl-local`) and install the app (when Chrome offers it). */
import { readMeta } from "@/lib/boot";
import { h } from "@/lib/dom";
import { watchInstall } from "@/phone/install";
import { openPairDialog } from "@/phone/pair-dialog";
import { phoneButton } from "@/phone/phone-button";

export interface PhoneTools {
  dispose: () => void;
  /** One persistent node: headers that repaint move it instead of rebuilding it. Hidden while it has no button. */
  el: HTMLElement;
}

export const isLocalPage = (): boolean => readMeta("todoimpl-local") === "1";

export function createPhoneTools(): PhoneTools {
  const element = h("span", { class: "phone-tools" });
  const pair = isLocalPage() ? phoneButton("qr", "Pair a phone", "pair", () => { openPairDialog(pair); }) : null;
  const install = phoneButton("install", "Install the app", "install", () => { void installer.install(); });
  const refresh = (): void => {
    install.hidden = !installer.canInstall();
    element.hidden = pair === null && install.hidden;
  };
  const installer = watchInstall(refresh);
  element.append(...(pair === null ? [] : [pair]), install);
  refresh();
  return { dispose: installer.dispose, el: element };
}
