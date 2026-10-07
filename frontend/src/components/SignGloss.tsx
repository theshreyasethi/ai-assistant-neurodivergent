import React, { useRef, useState } from 'react';

import api from '../services/api';

interface Props {
  text: string;
  lang?: string;
}

interface GlossaryEntry {
  term: string;
  lang: string;
  videoUrl: string;
  captions: string;
}

const WORD_RE = /[A-Za-z][A-Za-z'-]*/g;

/**
 * Tap/click (or focus + Enter) any word to open a captioned sign-language
 * clip, when the school has curated one (roadmap P4-04). Licence-safe by
 * construction — every clip this ever shows comes from backend/routers/
 * glossary.py, which only ever stores school-owned Firebase Storage URLs.
 */
const SignGloss: React.FC<Props> = ({ text, lang = 'asl' }) => {
  const [open, setOpen] = useState<{ term: string; entry: GlossaryEntry | null; loading: boolean } | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const lookup = async (term: string) => {
    setOpen({ term, entry: null, loading: true });
    try {
      const { data } = await api.get(`/api/glossary/${encodeURIComponent(term.toLowerCase())}`, { params: { lang } });
      setOpen({ term, entry: data, loading: false });
    } catch {
      setOpen({ term, entry: null, loading: false });
    }
  };

  const close = () => setOpen(null);

  const words = text.match(WORD_RE) ?? [];
  const parts = text.split(WORD_RE);

  return (
    <div className="relative">
      <p className="text-base leading-relaxed font-body">
        {parts.map((part, i) => (
          <React.Fragment key={i}>
            {part}
            {words[i] && (
              <button
                type="button"
                onClick={() => lookup(words[i])}
                className="underline decoration-dotted decoration-primary hover:bg-primary-container/20 rounded focus:ring-2 focus:ring-primary"
              >
                {words[i]}
              </button>
            )}
          </React.Fragment>
        ))}
      </p>

      {open && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-label={`Sign for ${open.term}`}
          className="absolute z-20 mt-2 w-72 glass-card rounded-2xl p-4 shadow-xl"
          onKeyDown={(e) => {
            if (e.key === 'Escape') close();
          }}
        >
          <div className="flex justify-between items-start mb-2">
            <h4 className="font-heading text-sm font-semibold">{open.term}</h4>
            <button type="button" onClick={close} aria-label="Close" className="text-on-surface-variant">
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          </div>
          {open.loading && <p className="text-xs text-on-surface-variant">Loading…</p>}
          {!open.loading && open.entry && (
            <>
              <video
                src={open.entry.videoUrl}
                controls
                className="w-full rounded-lg"
                aria-label={`Sign-language clip for ${open.term}`}
              />
              {open.entry.captions && (
                <p className="text-xs text-on-surface-variant font-body mt-2">{open.entry.captions}</p>
              )}
            </>
          )}
          {!open.loading && !open.entry && (
            <p className="text-xs text-on-surface-variant font-body">
              No sign clip for this word yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default SignGloss;
