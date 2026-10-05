"use client";

import { useState, useSyncExternalStore } from "react";

const motionQuery = "(prefers-reduced-motion: reduce)";
function subscribe(callback: () => void) {
  const preference = window.matchMedia(motionQuery);
  preference.addEventListener("change", callback);
  return () => preference.removeEventListener("change", callback);
}

/** Main-content loading only. The caller owns readiness, failure and retry. */
export function PageLoader({ fallback }: { fallback: React.ReactNode }) {
  const reducedMotion = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(motionQuery).matches,
    () => true,
  );
  const [unavailable, setUnavailable] = useState(false);
  if (reducedMotion || unavailable) return fallback;
  return (
    <div className="page-loader" role="status" aria-label="Carregando dados">
      <video
        ref={(video) => {
          if (video) video.playbackRate = 1.5;
        }}
        src="/media/up-loader.mp4"
        autoPlay
        muted
        playsInline
        loop
        preload="auto"
        aria-hidden="true"
        onError={() => setUnavailable(true)}
      />
      <span className="sr-only">Carregando dados</span>
    </div>
  );
}
