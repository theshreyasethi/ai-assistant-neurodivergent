import React, { useEffect, useRef, useState } from 'react';

import { useProfile } from '../hooks/useProfile';
import { NotifyEventDetail } from '../services/notify';
import { speakOnce } from '../services/speech';

/** Mount once (App.tsx). Renders notify() calls, speaking them for
 * blind/low-vision viewers and adding a vibration cue on top for deaf ones. */

const KIND_STYLE: Record<string, string> = {
  info: 'bg-surface-container-highest/95 border-outline-variant',
  success: 'bg-tertiary-container/95 border-tertiary text-on-tertiary-container',
  error: 'bg-error-container/95 border-error text-on-error-container',
  listening: 'bg-primary-container/95 border-primary text-on-primary-container',
  thinking: 'bg-surface-container-high/95 border-outline-variant',
};

const AccessibleNotification: React.FC = () => {
  const { profile } = useProfile();
  const [items, setItems] = useState<NotifyEventDetail[]>([]);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const onNotify = (e: Event) => {
      const detail = (e as CustomEvent<NotifyEventDetail>).detail;
      setItems((prev) => [...prev, detail]);

      // Never speak when the student runs their own screen reader — this
      // live region already reaches them via aria-live; our own TTS on top
      // would be a second voice talking over theirs.
      const speechWanted =
        !detail.silent &&
        profile.prefs.voiceEngine !== 'screenReader' &&
        (profile.prefs.ttsEnabled || profile.disabilities.some((d) => d === 'blind' || d === 'low_vision'));
      if (speechWanted) {
        speakOnce(detail.speak, { rate: profile.prefs.ttsRate || 1 });
      }

      timers.current[detail.id] = setTimeout(() => {
        setItems((prev) => prev.filter((i) => i.id !== detail.id));
        delete timers.current[detail.id];
      }, detail.durationMs);
    };

    window.addEventListener('app:notify', onNotify);
    return () => window.removeEventListener('app:notify', onNotify);
  }, [profile]);

  // The live-region container stays mounted (with role/aria-live already
  // present) even with zero items — many screen readers only announce
  // content added to an aria-live region that was ALREADY in the DOM when
  // they started watching it; a container that only appears alongside its
  // first message can miss that very message.
  return (
    <div
      className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full px-4 sm:px-0 pointer-events-none"
      aria-live={profile.prefs.captionsAlways ? 'assertive' : 'polite'}
      aria-atomic="true"
    >
      {items.map((item) => (
        <div
          key={item.id}
          role="status"
          className={`pointer-events-auto rounded-2xl border p-3 shadow-lg backdrop-blur-xl font-body text-sm ${
            KIND_STYLE[item.kind] ?? KIND_STYLE.info
          }`}
        >
          {item.message}
        </div>
      ))}
    </div>
  );
};

export default AccessibleNotification;
