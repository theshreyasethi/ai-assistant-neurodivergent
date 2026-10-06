import React from 'react';
import { useLocation } from 'react-router-dom';

import { useProfile } from '../hooks/useProfile';
import { getPageInfo } from '../config/pageRegistry';
import { earcon } from '../services/earcons';

/**
 * Mounted once (App.tsx), inside the Router. On every route change:
 *   1. sets document.title (WCAG 2.4.2),
 *   2. moves focus to the page's own <h1> if it has one (WCAG 2.4.3) —
 *      a screen-reader user following focus hears that heading
 *      automatically, which IS the announcement for them,
 *   3. announces the page through this component's own live region, but
 *      ONLY when that focus move didn't already cover it (no h1 on the
 *      page) or the student's engine is our own TTS rather than their own
 *      screen reader — never both, which is what "without double speech"
 *      means here.
 */
const RouteAnnouncer: React.FC = () => {
  const { pathname } = useLocation();
  const { profile } = useProfile();
  const [announcement, setAnnouncement] = React.useState('');
  const isFirstRun = React.useRef(true);

  React.useEffect(() => {
    const info = getPageInfo(pathname);
    document.title = `${info.title} – EduEase`;

    const h1 = document.querySelector<HTMLElement>('main h1');
    if (h1) {
      if (!h1.hasAttribute('tabindex')) h1.setAttribute('tabindex', '-1');
      h1.focus({ preventScroll: true });
    }

    // A student running their own screen reader (NVDA/JAWS/VoiceOver) just
    // heard the h1 via the focus move above (or will tab to it); our own
    // live region would be a second, redundant voice talking over theirs.
    const screenReaderUser = profile.prefs.voiceEngine === 'screenReader';
    setAnnouncement(screenReaderUser ? '' : h1 ? info.title : info.shortSummary);

    if (profile.prefs.voiceFirst && !isFirstRun.current) earcon.heading();
    isFirstRun.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <div role="status" aria-live="polite" className="sr-only">
      {announcement}
    </div>
  );
};

export default RouteAnnouncer;
