import { watchVersion } from "@/lib/version-watch";
import { defineUsage } from "@/usage/app";
import { defineTable } from "@/usage/table-element";

/** Page entry: register the elements and start the build watcher (reloads when the server reports another build). */
export function boot(): () => void {
  defineTable();
  defineUsage();
  return watchVersion();
}
