import { defineIssues } from "@/issues/app";
import { watchVersion } from "@/lib/version-watch";

/** Page entry: register the element and start the build watcher (reloads when the server reports another build). */
export function boot(): () => void {
  defineIssues();
  return watchVersion();
}
