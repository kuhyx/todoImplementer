import { watchVersion } from "@/lib/version-watch";
import { defineSessions } from "@/sessions/app";

/** Page entry: register the element and start the build watcher (reloads when the server reports another build). */
export function boot(): () => void {
  defineSessions();
  return watchVersion();
}
