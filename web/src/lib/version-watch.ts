/** Reload the page when /version reports another build than the one this page was served with. */
import { pageBuild } from "@/lib/boot";
import { getJson } from "@/lib/http";
import { poll } from "@/lib/poller";
import { routes } from "@/lib/routes";
import { version } from "@/lib/schemas";

export const VERSION_POLL_MS = 5000;

/** The real reload; tests swap `page.reload` (jsdom's `location` cannot be stubbed in a vm pool). */
export const page = { reload: (): void => { location.reload(); } };

export function watchVersion(reload: () => void = () => { page.reload(); }): () => void {
  let baseline = pageBuild();
  return poll(async () => {
    try {
      const { build } = await getJson(routes.version, version);
      baseline ??= build;
      if (build !== baseline) reload();
    } catch {
      /* A failed poll is not a new build; the board banner already reports an unreachable server. */
    }
  }, VERSION_POLL_MS);
}
