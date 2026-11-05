/** Run `task` now, then every `ms`: never overlapping, skipped while hidden, immediate on return. */
export function poll(task: () => Promise<void>, ms: number): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let isStopped = false;
  const hasStopped = (): boolean => isStopped;
  let isRunning = false;

  const tick = async (): Promise<void> => {
    clearTimeout(timer);
    if (isRunning || hasStopped()) return;
    if (!document.hidden) {
      isRunning = true;
      try {
        await task();
      } catch (error) {
        console.error("poll task failed", error);
      } finally {
        isRunning = false;
      }
    }
    if (!hasStopped()) timer = setTimeout(() => void tick(), ms);
  };
  const onVisible = (): void => {
    if (!document.hidden) void tick();
  };

  document.addEventListener("visibilitychange", onVisible);
  void tick();
  return () => {
    isStopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
