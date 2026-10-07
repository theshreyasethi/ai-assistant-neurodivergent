import React, { useEffect, useRef, useState } from 'react';

import { CAPTION_ADDED_EVENT, CaptionEntry, getCaptions } from '../services/captions';
import { KIND_ICON, KIND_WORD, NotifyEventDetail } from '../services/notify';

/**
 * Non-audio notification channels (roadmap P4-02): a border pulse and a
 * small badge, both icon+word (never colour alone), plus the persistent
 * caption log drawer. Mounted once in App.tsx, alongside — not instead of
 * — <AccessibleNotification/>, which owns the toast channel.
 *
 * The border pulse is capped at <=3 flashes/second and a low luminance
 * change (WCAG 2.3.1 — general flash threshold), and is skipped entirely
 * under prefers-reduced-motion via the `motion-safe:` Tailwind variant
 * already used throughout this codebase.
 */
const VisualAlert: React.FC = () => {
  const [pulseKind, setPulseKind] = useState<NotifyEventDetail['kind'] | null>(null);
  const [badge, setBadge] = useState<NotifyEventDetail | null>(null);
  const [captions, setCaptions] = useState<CaptionEntry[]>([]);
  const [logOpen, setLogOpen] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const badgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onNotify = (e: Event) => {
      const detail = (e as CustomEvent<NotifyEventDetail>).detail;
      if (detail.channels.includes('borderPulse')) {
        setPulseKind(detail.kind);
        if (pulseTimer.current) clearTimeout(pulseTimer.current);
        pulseTimer.current = setTimeout(() => setPulseKind(null), 1200);
      }
      if (detail.channels.includes('badge')) {
        setBadge(detail);
        if (badgeTimer.current) clearTimeout(badgeTimer.current);
        badgeTimer.current = setTimeout(() => setBadge(null), detail.durationMs);
      }
    };
    window.addEventListener('app:notify', onNotify);
    return () => window.removeEventListener('app:notify', onNotify);
  }, []);

  useEffect(() => {
    setCaptions(getCaptions());
    const onCaption = () => setCaptions(getCaptions());
    window.addEventListener(CAPTION_ADDED_EVENT, onCaption);
    return () => window.removeEventListener(CAPTION_ADDED_EVENT, onCaption);
  }, []);

  const pulseColor: Record<string, string> = {
    info: 'border-primary',
    success: 'border-tertiary',
    error: 'border-error',
    listening: 'border-primary',
    thinking: 'border-outline-variant',
  };

  return (
    <>
      {/* Border pulse: a 2px viewport-edge ring, never the only cue — the
          toast (AccessibleNotification) and caption log both carry the same
          message in text. */}
      {pulseKind && (
        <div
          aria-hidden="true"
          className={`fixed inset-2 z-[90] pointer-events-none rounded-3xl border-2 motion-safe:animate-pulse ${
            pulseColor[pulseKind] ?? 'border-primary'
          }`}
          style={{ animationDuration: '400ms', animationIterationCount: 3 }}
        />
      )}

      {/* Badge: icon + word, top-center, for a persistent-ish state like
          "Listening" — distinct from the bottom-right toast stack. */}
      {badge && (
        <div
          role="status"
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[95] flex items-center gap-2 px-4 py-2 rounded-full glass-card shadow-lg font-heading text-sm font-semibold"
        >
          <span className="material-symbols-outlined text-primary" aria-hidden="true">
            {KIND_ICON[badge.kind]}
          </span>
          <span>{KIND_WORD[badge.kind]}: {badge.message}</span>
        </div>
      )}

      {/* Persistent caption log — everything the app has spoken or
          announced, independent of whether audio was ever on. */}
      <div className="fixed bottom-4 left-4 z-[90]">
        <button
          type="button"
          onClick={() => setLogOpen((v) => !v)}
          aria-expanded={logOpen}
          aria-controls="caption-log-panel"
          className="flex items-center gap-2 px-3 py-2 rounded-full glass-card shadow-md font-heading text-xs font-semibold text-on-surface-variant"
        >
          <span className="material-symbols-outlined text-base" aria-hidden="true">closed_caption</span>
          Captions
        </button>
        {logOpen && (
          <div
            id="caption-log-panel"
            role="log"
            aria-label="Caption history"
            className="mt-2 w-80 max-h-64 overflow-y-auto glass-card rounded-2xl p-3 shadow-xl text-sm font-body"
          >
            {captions.length === 0 ? (
              <p className="text-on-surface-variant text-xs">Nothing announced yet.</p>
            ) : (
              <ul className="space-y-1">
                {captions.slice(-50).reverse().map((c) => (
                  <li key={c.id} className="text-on-surface border-b border-outline-variant/30 pb-1 last:border-0">
                    {c.text}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </>
  );
};

export default VisualAlert;
