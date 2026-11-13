/** Chrome's install prompt: keep the event until kuhy taps the install button. No service worker is involved (a caching one would serve stale builds). */

interface InstallEvent extends Event {
  prompt: () => Promise<void>;
}

export interface Installer {
  canInstall: () => boolean;
  dispose: () => void;
  /** Show Chrome's own dialog; the stashed event works once, so the button goes away either way. */
  install: () => Promise<void>;
}

export const isStandalone = (): boolean => matchMedia("(display-mode: standalone)").matches;

export function watchInstall(onChange: () => void): Installer {
  let offered: InstallEvent | null = null;
  const onOffer = (event: Event): void => {
    // Without this Chrome shows its own mini-infobar next to our button.
    event.preventDefault();
    if (isStandalone()) return;
    offered = event as InstallEvent;
    onChange();
  };
  const onInstalled = (): void => {
    offered = null;
    onChange();
  };
  addEventListener("beforeinstallprompt", onOffer);
  addEventListener("appinstalled", onInstalled);
  return {
    canInstall: () => offered !== null && !isStandalone(),
    dispose: () => {
      removeEventListener("beforeinstallprompt", onOffer);
      removeEventListener("appinstalled", onInstalled);
    },
    install: async () => {
      const event = offered;
      offered = null;
      onChange();
      await event?.prompt();
    },
  };
}
