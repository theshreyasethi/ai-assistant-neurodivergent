import React from 'react';

interface Props {
  title: string;
  /** One-sentence plain-language summary of what the chart shows — the
   * aria-label for the chart itself AND the content a screen-reader user
   * gets without needing to open the table twin. */
  summary: string;
  children: React.ReactNode;
  /** The same data as an actual <table> — every chart in the teacher
   * dashboard must have one (roadmap P5-05); a screen-reader user gets
   * the same information a sighted user gets from the chart, never less. */
  tableChildren: React.ReactNode;
}

/**
 * Accessible chart wrapper enforced across every teacher-dashboard
 * visualisation (roadmap P5-05): role="img" with a plain-language
 * summary, a visible caption, and a collapsible table twin. No chart in
 * this app should ever render without going through this.
 */
const ChartFrame: React.FC<Props> = ({ title, summary, children, tableChildren }) => (
  <figure className="glass-card rounded-3xl p-6">
    <figcaption className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-4">
      {title}
    </figcaption>
    <div role="img" aria-label={summary}>
      {children}
    </div>
    <details className="mt-3">
      <summary className="font-heading text-xs font-semibold text-primary cursor-pointer">
        View as table
      </summary>
      <div className="mt-2 overflow-x-auto">{tableChildren}</div>
    </details>
  </figure>
);

export default ChartFrame;
