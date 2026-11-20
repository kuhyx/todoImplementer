/** The header's install button (when Chrome offers it); the QR pair button is gone (kuhy, 2026-11-20). */
import { h } from "@/lib/dom";
import { watchInstall } from "@/phone/install";
import { phoneButton } from "@/phone/phone-button";

export interface PhoneTools {
  dispose: () => void;
  /** One persistent node: headers that repaint move it instead of rebuilding it. Hidden while it has no button. */
  el: HTMLElement;
}

export function createPhoneTools(): PhoneTools {
  const element = h("span", { class: "phone-tools" });
  const install = phoneButton("install", "Install the app", "install", () => { void installer.install(); });
  const refresh = (): void => {
    install.hidden = !installer.canInstall();
    element.hidden = install.hidden;
  };
  const installer = watchInstall(refresh);
  element.append(install);
  refresh();
  return { dispose: installer.dispose, el: element };
}
