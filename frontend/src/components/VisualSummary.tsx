import React, { useEffect, useRef, useState } from 'react';

import api from '../services/api';
import { getCurrentSession, track } from '../services/telemetry';
import type { VisualEvent } from '../services/telemetry';

interface Concept {
  title: string;
  explanation: string;
  emoji: string;
}

interface VisualSummaryData {
  diagram: string | null;
  diagramType: string | null;
  concepts: Concept[];
  degraded: boolean;
}

interface Props {
  text: string;
  profile: string;
  studentId: string | null;
  contentId?: string | null;
}

const DWELL_THRESHOLD_MS = 3000;

/**
 * Deaf/HoH visual-summary panel (roadmap P4-01) — a Mermaid diagram + concept
 * cards generated from the lesson text, with a text-only fallback that is
 * ALWAYS present (never the diagram/cards as the sole representation).
 *
 * Fired only on an explicit "Show visual summary" click, never automatically
 * on page load — this is a real LLM call, and most students never need it.
 */
const VisualSummary: React.FC<Props> = ({ text, profile, studentId, contentId }) => {
  const [data, setData] = useState<VisualSummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [svg, setSvg] = useState<string | null>(null);
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());
  const dwellStartRef = useRef<Record<number, number>>({});
  const dwellTrackedRef = useRef<Set<number>>(new Set());

  const trackVisual = (overrides: Partial<Pick<VisualEvent, 'conceptTitle' | 'dwellMs' | 'expanded' | 'replayed'>>) => {
    const sessionId = getCurrentSession();
    if (!sessionId || !studentId) return;
    const event: VisualEvent = {
      type: 'visual',
      sessionId,
      studentId,
      ts: Date.now(),
      contentId: contentId ?? null,
      conceptTitle: null,
      dwellMs: 0,
      expanded: false,
      replayed: false,
      ...overrides,
    };
    track(event);
  };

  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const { data: resp } = await api.post('/api/visual-summary', { text, profile });
      setData(resp);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!data?.diagram) {
      setSvg(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
        const { svg: rendered } = await mermaid.render(`visual-summary-${Date.now()}`, data.diagram!);
        if (!cancelled) setSvg(rendered);
      } catch (err) {
        console.warn('[VisualSummary] mermaid render failed, falling back to cards only', err);
        if (!cancelled) setSvg(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [data?.diagram]);

  const onCardFocusIn = (idx: number) => {
    dwellStartRef.current[idx] = Date.now();
  };
  const onCardFocusOut = (idx: number) => {
    const start = dwellStartRef.current[idx];
    if (!start) return;
    const dwellMs = Date.now() - start;
    delete dwellStartRef.current[idx];
    if (dwellMs >= DWELL_THRESHOLD_MS && !dwellTrackedRef.current.has(idx)) {
      dwellTrackedRef.current.add(idx);
      trackVisual({ conceptTitle: data?.concepts[idx]?.title ?? null, dwellMs });
    }
  };

  const toggleCard = (idx: number) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      const wasExpanded = next.has(idx);
      if (wasExpanded) next.delete(idx);
      else {
        next.add(idx);
        trackVisual({ conceptTitle: data?.concepts[idx]?.title ?? null, expanded: true });
      }
      return next;
    });
  };

  const replayDiagram = () => {
    trackVisual({ replayed: true });
  };

  const ariaLabel = data?.concepts.length
    ? `Visual summary. Concepts: ${data.concepts.map((c) => c.title).join(', ')}.`
    : 'Visual summary';

  if (!data) {
    return (
      <div className="glass-card rounded-3xl p-6">
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="px-5 py-2.5 rounded-xl font-heading text-sm font-semibold bg-primary text-white shadow-md disabled:opacity-60"
        >
          {loading ? 'Building visual summary…' : 'Show visual summary'}
        </button>
        {error && (
          <p role="alert" className="text-error text-sm mt-2 font-body">
            Could not build a visual summary right now. Try again shortly.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="glass-card rounded-3xl p-6 space-y-6">
      {data.degraded && (
        <p role="status" className="text-xs text-on-surface-variant font-body">
          Visual summary is running in a limited mode right now.
        </p>
      )}

      {svg && (
        <figure>
          <figcaption className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">
            Diagram
          </figcaption>
          <div role="img" aria-label={ariaLabel} className="overflow-x-auto" dangerouslySetInnerHTML={{ __html: svg }} />
          <button
            type="button"
            onClick={replayDiagram}
            className="mt-2 text-xs font-heading font-semibold text-primary underline"
          >
            Replay diagram
          </button>
        </figure>
      )}

      {data.concepts.length > 0 && (
        <div>
          <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-3">
            Key concepts
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.concepts.map((concept, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => toggleCard(idx)}
                onFocus={() => onCardFocusIn(idx)}
                onBlur={() => onCardFocusOut(idx)}
                onMouseEnter={() => onCardFocusIn(idx)}
                onMouseLeave={() => onCardFocusOut(idx)}
                aria-expanded={expandedCards.has(idx)}
                className="text-left p-4 rounded-2xl bg-surface-container-low border border-white/40 hover:border-primary-container transition-all"
              >
                <span className="text-2xl" aria-hidden="true">{concept.emoji}</span>
                <p className="font-heading text-sm font-semibold mt-1">{concept.title}</p>
                {expandedCards.has(idx) && (
                  <p className="text-sm text-on-surface-variant font-body mt-2">{concept.explanation}</p>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Text alternative — ALWAYS present, never only the diagram/cards. */}
      <details className="text-sm">
        <summary className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest cursor-pointer">
          View as text
        </summary>
        <ul className="mt-2 space-y-1 list-disc list-inside font-body">
          {data.concepts.map((c, idx) => (
            <li key={idx}>
              <strong>{c.title}:</strong> {c.explanation}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
};

export default VisualSummary;
