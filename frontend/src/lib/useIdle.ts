import { useEffect, useRef } from 'react';

export const IDLE_SECONDS = 45;
const ACTIVITY = ['keydown', 'pointerdown', 'pointermove', 'scroll', 'input', 'touchstart'];

/**
 * Reports once when the Client has done nothing for IDLE_SECONDS on an incomplete Step.
 * The server decides whether that earns Supportive content (once per Step).
 */
export function useIdle(onIdle: (seconds: number) => void, active: boolean, step: string) {
  const callback = useRef(onIdle);
  callback.current = onIdle;

  useEffect(() => {
    if (!active) return;
    let timer = 0;
    let reported = false;
    const reset = () => {
      window.clearTimeout(timer);
      if (reported) return;
      timer = window.setTimeout(() => {
        reported = true;
        callback.current(IDLE_SECONDS);
      }, IDLE_SECONDS * 1000);
    };
    ACTIVITY.forEach((event) => window.addEventListener(event, reset, { passive: true }));
    reset();
    return () => {
      window.clearTimeout(timer);
      ACTIVITY.forEach((event) => window.removeEventListener(event, reset));
    };
  }, [active, step]);
}
