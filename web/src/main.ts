/** Page entry: register the elements and start the build watcher. */
import { defineApp } from "@/components/app";
import { defineDrawer } from "@/components/drawer";
import { watchVersion } from "@/lib/version-watch";

export function boot(): () => void {
  defineDrawer();
  defineApp();
  return watchVersion();
}

boot();
