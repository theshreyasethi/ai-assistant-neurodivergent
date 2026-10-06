import React, { useEffect, useRef } from 'react';

export interface QuizCardQuestion {
  questionId?: string;
  question: string;
  options: string[];
  topic?: string;
  question_type?: 'fill_blank' | 'true_false' | 'mcq';
}

interface QuizCardProps {
  question: QuizCardQuestion;
  index: number;
  total: number;
  selectedAnswer: string | null;
  typedAnswer: string;
  onSelect: (option: string) => void;
  onTypedChange: (value: string) => void;
  onSubmit: () => void;
  /** Blind, dyslexia, dysgraphia and motor profiles get A/B/C/D options for
   * fill_blank instead of a free-text box — "answer B" has nothing to
   * select against free text, and typing is itself the barrier for some
   * of these profiles (roadmap task P2-07 / patent-readiness finding B07). */
  showOptionsForFillBlank: boolean;
  /** First pointer/key event on this question (roadmap P3-01) — measures
   * timeToFirstInteractionMs instead of hard-coding it to null. */
  onInteract?: () => void;
  /** Focus returned to the question stem after an option was already
   * touched — counted as a revisit (roadmap P3-01). */
  onStemRefocus?: () => void;
}

const OPTION_LETTERS = ['A', 'B', 'C', 'D'];

/**
 * Accessible, voice-operable quiz question. A <fieldset>/<legend> group
 * (screen readers announce the legend once per group, not once per radio),
 * a live announcement when the question changes, and roving focus so
 * arrow keys move between options the way native radio groups expect.
 */
const QuizCard: React.FC<QuizCardProps> = ({
  question, index, total, selectedAnswer, typedAnswer, onSelect, onTypedChange, onSubmit, showOptionsForFillBlank,
  onInteract, onStemRefocus,
}) => {
  const qType = question.question_type || 'fill_blank';
  const touchedOptionsRef = useRef(false);
  useEffect(() => {
    touchedOptionsRef.current = false;
  }, [index, question.questionId]);
  const typeBadge =
    qType === 'mcq' ? { label: 'Multiple Choice', cls: 'bg-primary-fixed text-on-primary-fixed-variant' } :
    qType === 'true_false' ? { label: 'True or False', cls: 'bg-tertiary-fixed text-on-tertiary-fixed-variant' } :
    { label: 'Fill in the Blank', cls: 'bg-secondary-container text-on-surface' };

  const usesOptions = qType === 'mcq' || qType === 'true_false' || (qType === 'fill_blank' && showOptionsForFillBlank);
  const legendId = `question-${index}-legend`;

  return (
    <fieldset
      className="glass-card rounded-3xl p-6 md:p-8 col-span-12 md:col-span-8 border-0"
      onPointerDownCapture={onInteract}
      onKeyDownCapture={onInteract}
    >
      <legend id={legendId} className="mb-6 w-full">
        <span className={`font-heading text-xs font-semibold px-3 py-1 rounded-full ${typeBadge.cls}`}>{typeBadge.label}</span>
        {/* Announced once per question change via this live region, so a
            screen-reader user hears "Question 3 of 9" without needing to
            re-read the whole card. */}
        <span role="status" aria-live="polite" className="sr-only">
          Question {index + 1} of {total}, {typeBadge.label}.
        </span>
        <h2
          className="font-heading text-xl md:text-2xl font-semibold mt-3 text-on-surface"
          tabIndex={-1}
          onFocus={() => {
            // Only a REvisit if an option was already touched — the initial
            // mount/auto-focus of the stem itself isn't a revisit.
            if (touchedOptionsRef.current) onStemRefocus?.();
          }}
        >
          {question.question}
        </h2>
      </legend>

      {usesOptions && (
        <div className={`grid gap-3 ${qType === 'true_false' ? 'grid-cols-2' : 'grid-cols-1'}`} role="radiogroup" aria-labelledby={legendId}>
          {question.options.map((option, optIdx) => {
            const inputId = `q${index}-opt${optIdx}`;
            const isChecked = selectedAnswer === option;
            return (
              <label
                key={optIdx}
                htmlFor={inputId}
                className={`group relative flex items-center p-4 border-2 rounded-xl cursor-pointer transition-all ${
                  isChecked ? 'border-primary bg-primary-container/10' : 'border-surface-variant hover:border-primary-container'
                }`}
              >
                <input
                  id={inputId}
                  type="radio"
                  name={`quiz-q${index}`}
                  value={option}
                  checked={isChecked}
                  onChange={() => { touchedOptionsRef.current = true; onSelect(option); }}
                  className="w-5 h-5 text-primary border-outline focus:ring-primary"
                />
                <span className="ml-3 shrink-0 font-heading text-xs font-bold text-on-surface-variant uppercase" aria-hidden="true">
                  {OPTION_LETTERS[optIdx] ?? ''}.
                </span>
                <span className={`ml-2 text-base font-body ${isChecked ? 'text-primary font-semibold' : 'text-on-surface group-hover:text-primary'} transition-colors`}>
                  {option}
                </span>
              </label>
            );
          })}
        </div>
      )}

      {qType === 'fill_blank' && !showOptionsForFillBlank && (
        <div className="relative">
          <label htmlFor="fill-blank-answer" className="sr-only">Your answer</label>
          <input
            id="fill-blank-answer"
            type="text"
            value={typedAnswer}
            onChange={(e) => { touchedOptionsRef.current = true; onTypedChange(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && typedAnswer.trim()) onSubmit();
            }}
            placeholder="Enter your answer..."
            className="w-full bg-surface-container-low border-2 border-outline-variant rounded-xl p-4 focus:border-primary focus:ring-0 transition-all font-body text-base"
            autoFocus
          />
        </div>
      )}
    </fieldset>
  );
};

export default QuizCard;
