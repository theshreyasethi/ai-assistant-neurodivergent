import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../services/api";
import Eye from "../components/Eye";
import QuizCard from "../components/QuizCard";
import { useProfile } from "../hooks/useProfile";
import { canUseWebcam, scoringProfile } from "../types/profile";
import { earcon } from "../services/earcons";
import { speakOnce } from "../services/speech";
import { useVoiceCommand } from "../hooks/useVoiceCommand";
import { useQuestionTelemetry } from "../hooks/useQuestionTelemetry";
import { endSession, FocusMeter, setCurrentSession, startSession, track, triggerEvaluation } from "../services/telemetry";

interface Question {
  questionId?: string;
  conceptId?: string | null;
  question: string;
  options: string[];
  answer: string;
  topic?: string;
  difficulty?: number;
  question_type?: "fill_blank" | "true_false" | "mcq";
  /** Autism/PATTERN (roadmap P3-07): sequence/category/matching tag from
   * services/quiz_gen.py. */
  itemKind?: string | null;
  /** Closed-loop re-presentation (roadmap P3-03) — a pre-generated easier
   * variant of the same concept, served when a wrong answer is classified
   * as a confident COMPREHENSION_BARRIER. */
  simplerQuestion?: string | null;
  simplerOptions?: string[] | null;
  simplerAnswer?: string | null;
  /** Bumped to 2 once this slot has been swapped for its simpler variant —
   * also used as part of the telemetry reset key below, since the
   * questionId itself deliberately stays the same (the idempotency key in
   * routers/telemetry.py already disambiguates by attempts). */
  attempts?: number;
}

const OPTION_LETTERS = ["A", "B", "C", "D"];

// These profiles get A/B/C/D options for fill_blank questions instead of a
// free-text box — "answer B" has nothing to select against free text, and
// for dysgraphia/motor, typing itself is the barrier being worked around
// (roadmap task P2-07 / patent-readiness finding B07).
const FILL_BLANK_OPTIONS_PROFILES = new Set(["blind", "low_vision", "dyslexia", "dysgraphia", "motor"]);

const QuizPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { text } = location.state || { text: "" };
  const { uid, profile, consent, gradeLevel, loading: profileLoading } = useProfile();

  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [typedAnswer, setTypedAnswer] = useState("");
  const [score, setScore] = useState(0);
  const [isQuizCompleted, setIsQuizCompleted] = useState(false);
  const [wrongTopics, setWrongTopics] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  // Whole-quiz degraded flag (services/quiz_gen.py's spaCy fallback, used
  // when the LLM was unreachable) — propagated onto every tracked
  // QuestionEvent so the engine excludes these items from DASE entirely
  // (roadmap P3-11).
  const [quizDegraded, setQuizDegraded] = useState(false);

  const MAX_QUESTIONS = 10;

  // ─── DASE telemetry (DATA_CONTRACT §3.1) ───
  const sessionIdRef = useRef<string | null>(null);
  const quizStartRef = useRef<number>(Date.now());
  const focusMeterRef = useRef(new FocusMeter());
  // Correct-answer times this session, oldest first — the closed loop's own
  // comparison set for POST /api/classify (distinct from the backend's
  // cross-session student_baselines, which /api/evaluate reads separately).
  const priorTimesRef = useRef<number[]>([]);
  // Which original questionIds have already been re-presented once —
  // the closed loop fires at most once per question, even if the simpler
  // variant is ALSO answered wrong.
  const representedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (text && !profileLoading) {
      api
        .post("/generate-quiz/", {
          text,
          profile: scoringProfile(profile),
          grade_level: gradeLevel ?? undefined,
        })
        .then((res) => {
          const data = res.data.questions.slice(0, MAX_QUESTIONS);
          setQuestions(data);
          setQuizDegraded(!!res.data.degraded);
        })
        .catch((err) => console.error("Error fetching quiz:", err))
        .finally(() => setLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, profileLoading]);

  // Open a telemetry session once we know who the student is and have
  // questions, and register it globally so VoiceNavigator's VoiceEvent
  // telemetry attributes to it (roadmap task P2-04).
  useEffect(() => {
    if (profileLoading || !uid || !questions.length || sessionIdRef.current) return;
    let cancelled = false;
    startSession(uid, "quiz").then((id) => {
      if (!cancelled) {
        sessionIdRef.current = id;
        if (id) setCurrentSession(id);
        quizStartRef.current = Date.now();
      }
    });
    return () => {
      cancelled = true;
    };
  }, [profileLoading, uid, questions.length]);

  useEffect(() => {
    return () => setCurrentSession(null);
  }, []);

  const totalQuestions = questions.length;
  const currentQuestion = questions[currentIndex];
  const qType = currentQuestion?.question_type || "fill_blank";
  const showFillBlankOptions =
    qType === "fill_blank" && profile.disabilities.some((d) => FILL_BLANK_OPTIONS_PROFILES.has(d));

  // Re-keyed on attempts (not just currentIndex): a closed-loop
  // re-presentation (roadmap P3-03) replaces the question IN PLACE at the
  // same index with the same questionId, so attempts flipping 1 -> 2 is
  // what tells this hook a fresh question actually started.
  const qt = useQuestionTelemetry(`${currentIndex}:${currentQuestion?.attempts ?? 1}`);

  // Announce + earcon on every new question, for voice-first students.
  useEffect(() => {
    if (!currentQuestion || loading || isQuizCompleted) return;
    if (profile.prefs.voiceFirst) {
      earcon.question();
      const optionsLine =
        qType === "fill_blank" && !showFillBlankOptions
          ? ""
          : ` Options: ${currentQuestion.options.map((o, i) => `${OPTION_LETTERS[i]}, ${o}`).join('. ')}.`;
      speakOnce(`Question ${currentIndex + 1} of ${totalQuestions}. ${currentQuestion.question}${optionsLine}`, {
        rate: profile.prefs.ttsRate || 1,
        lang: profile.prefs.speechLang,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, loading, isQuizCompleted, currentQuestion?.question]);

  const getCurrentAnswer = (): string | null => {
    const q = questions[currentIndex];
    if (!q) return null;
    if (q.question_type === "fill_blank" && !showFillBlankOptions) return typedAnswer.trim() || null;
    return selectedAnswer;
  };

  const handleSubmit = async () => {
    const userAnswer = getCurrentAnswer();
    if (!userAnswer) return;

    const currentQ = questions[currentIndex];
    const isCorrect =
      currentQ.question_type === "fill_blank" && !showFillBlankOptions
        ? userAnswer.toLowerCase() === currentQ.answer.toLowerCase()
        : userAnswer === currentQ.answer;

    const topicLabel = currentQ.topic || currentQ.answer;
    const sig = qt.snapshot();
    const { focusRatio, focusSamples } = focusMeterRef.current.read();
    const attempts = currentQ.attempts ?? 1;

    // Closed loop (roadmap P3-03): classify synchronously on a wrong answer,
    // before tracking the event, so the classification travels WITH it
    // rather than needing a second write.
    let classification = null;
    let shouldRepresent = false;
    if (!isCorrect) {
      try {
        const { data } = await api.post("/api/classify", {
          timeMs: sig.timeMs,
          priorTimesMs: priorTimesRef.current,
          focusRatio,
          focusSamples,
          answerChanges: sig.answerChanges,
          timeToFirstInteractionMs: sig.timeToFirstInteractionMs,
          reRead: sig.reRead,
          timedOut: false,
          hasSimplerVariant: !!currentQ.simplerQuestion,
        });
        classification = data.classification;
        shouldRepresent = !!data.shouldRepresent;
      } catch (err) {
        console.warn("[quiz] classify failed; continuing without a label", err);
      }
    }

    const willRepresent =
      shouldRepresent &&
      attempts < 2 &&
      !representedRef.current.has(currentQ.questionId || `q${currentIndex}`) &&
      !!currentQ.simplerQuestion &&
      !!currentQ.simplerOptions &&
      !!currentQ.simplerAnswer;

    if (sessionIdRef.current && uid) {
      track({
        type: "question",
        sessionId: sessionIdRef.current,
        studentId: uid,
        ts: Date.now(),
        questionId: currentQ.questionId || `q${currentIndex}`,
        conceptId: currentQ.conceptId ?? null,
        topic: currentQ.topic ?? null,
        difficulty: currentQ.difficulty ?? 3,
        questionType: currentQ.question_type ?? "mcq",
        itemKind: currentQ.itemKind ?? null,
        selected: userAnswer,
        correct: isCorrect,
        timeMs: sig.timeMs,
        timeToFirstInteractionMs: sig.timeToFirstInteractionMs,
        attempts,
        answerChanges: sig.answerChanges,
        hintsUsed: 0,
        revisits: sig.revisits,
        reRead: sig.reRead,
        focusRatio,
        focusSamples,
        isRepresentation: attempts > 1,
        originalQuestionId: attempts > 1 ? currentQ.questionId ?? null : null,
        classification,
        classifierVersion: null, // stamped server-side on ingest
        degraded: quizDegraded,
      });
      focusMeterRef.current.reset();
    }
    if (isCorrect) priorTimesRef.current.push(sig.timeMs);

    if (isCorrect) {
      setScore((prev) => prev + 1);
      if (profile.prefs.voiceFirst) speakOnce("Correct.", { rate: profile.prefs.ttsRate || 1 });
    } else if (!willRepresent) {
      setWrongTopics((prev) => [...prev, topicLabel]);
      if (profile.prefs.voiceFirst) speakOnce("Recorded.", { rate: profile.prefs.ttsRate || 1 });
    }

    if (willRepresent) {
      // Swap this slot for its simpler variant IN PLACE — same index, same
      // questionId, attempts bumped to 2. The idempotency key in
      // routers/telemetry.py already disambiguates by attempts, so this
      // question's second attempt is tracked as its own event rather than
      // overwriting the first.
      representedRef.current.add(currentQ.questionId || `q${currentIndex}`);
      setQuestions((prev) =>
        prev.map((q, i) =>
          i === currentIndex
            ? { ...q, question: q.simplerQuestion!, options: q.simplerOptions!, answer: q.simplerAnswer!, attempts: 2 }
            : q,
        ),
      );
      setSelectedAnswer(null);
      setTypedAnswer("");
      if (profile.prefs.voiceFirst) speakOnce("Let's try that a different way.", { rate: profile.prefs.ttsRate || 1 });
      return;
    }

    const isFinal = currentIndex >= totalQuestions - 1;
    if (!isFinal) {
      setCurrentIndex((prev) => prev + 1);
      setSelectedAnswer(null);
      setTypedAnswer("");
    } else {
      const finalScore = score + (isCorrect ? 1 : 0);
      const finalWrong = isCorrect ? wrongTopics : [...wrongTopics, topicLabel];
      setIsQuizCompleted(true);
      api.post("/analytics/log-quiz/", {
        score: finalScore,
        total_questions: totalQuestions,
        wrong_topics: [...new Set(finalWrong)],
      }).catch(() => {});

      if (sessionIdRef.current && uid) {
        const { focusRatio: finalFocusRatio } = focusMeterRef.current.read();
        endSession(sessionIdRef.current, {
          totalQuestions,
          correct: finalScore,
          totalTimeMs: Date.now() - quizStartRef.current,
          completed: true,
          meanFocusRatio: finalFocusRatio,
        }).then(() => triggerEvaluation(sessionIdRef.current, uid, scoringProfile(profile)));
      }
    }
  };

  const handleRestart = () => {
    setCurrentIndex(0);
    setScore(0);
    setWrongTopics([]);
    setSelectedAnswer(null);
    setTypedAnswer("");
    setIsQuizCompleted(false);
    representedRef.current.clear();
    priorTimesRef.current = [];
  };

  const hasAnswer = qType === "fill_blank" && !showFillBlankOptions ? typedAnswer.trim().length > 0 : !!selectedAnswer;

  // ── Voice commands (roadmap task P2-04/P2-07/P3-01) ──
  useVoiceCommand("ANSWER", (intent) => {
    const idx = intent.slots.optionIndex as number;
    const option = currentQuestion?.options[idx];
    if (option) {
      qt.onInteract();
      qt.onSelect(option);
      setSelectedAnswer(option);
    }
  });
  useVoiceCommand("SUBMIT", () => {
    if (hasAnswer) handleSubmit();
  });
  useVoiceCommand("REPEAT", () => {
    if (!currentQuestion) return;
    qt.onReplayQuestion();
    const optionsLine =
      qType === "fill_blank" && !showFillBlankOptions
        ? ""
        : ` Options: ${currentQuestion.options.map((o, i) => `${OPTION_LETTERS[i]}, ${o}`).join(". ")}.`;
    speakOnce(`${currentQuestion.question}${optionsLine}`, { rate: profile.prefs.ttsRate || 1, lang: profile.prefs.speechLang });
  });
  useVoiceCommand("PROGRESS", () => {
    speakOnce(`Question ${currentIndex + 1} of ${totalQuestions}. ${score} correct so far.`, { rate: profile.prefs.ttsRate || 1 });
  });

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <p className="font-heading text-lg text-on-surface-variant animate-pulse" role="status">Loading quiz...</p>
      </div>
    );
  }

  if (isQuizCompleted) {
    const uniqueWeakAreas = [...new Set(wrongTopics)];
    const pct = totalQuestions > 0 ? Math.round((score / totalQuestions) * 100) : 0;
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (pct / 100) * circumference;

    return (
      <div className="max-w-[1400px] mx-auto px-4 md:px-12 py-8 animate-fade-in">
        <div className="bento-grid">
          {/* Score Card */}
          <div className="col-span-12 md:col-span-4 glass-card rounded-3xl p-8 flex flex-col items-center text-center">
            <h3 className="font-heading text-xl font-semibold text-on-surface mb-6">Quiz Performance</h3>
            <div className="relative w-40 h-40 mb-6">
              <svg className="w-full h-full" viewBox="0 0 100 100" style={{transform: "rotate(-90deg)"}}>
                <circle cx="50" cy="50" r="45" fill="transparent" stroke="#e5eeff" strokeWidth="8" />
                <circle cx="50" cy="50" r="45" fill="transparent" stroke="#2a14b4" strokeWidth="8"
                  strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
                  style={{transition: "stroke-dashoffset 1s ease-out"}} />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="font-heading text-4xl font-bold text-primary">{pct}%</span>
              </div>
            </div>
            <p className="text-base text-on-surface-variant font-body">{score}/{totalQuestions} correct answers</p>
          </div>

          {/* Metrics */}
          <div className="col-span-12 md:col-span-8 glass-card rounded-3xl p-8">
            <h3 className="font-heading text-xl font-semibold text-on-surface mb-6">Session Summary</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-surface-container-low p-4 rounded-2xl">
                <span className="material-symbols-outlined text-primary mb-2 block">check_circle</span>
                <p className="text-xs text-on-surface-variant uppercase tracking-wider font-heading font-semibold">Correct</p>
                <p className="font-heading text-2xl font-bold text-on-surface">{score}</p>
              </div>
              <div className="bg-surface-container-low p-4 rounded-2xl">
                <span className="material-symbols-outlined text-error mb-2 block">cancel</span>
                <p className="text-xs text-on-surface-variant uppercase tracking-wider font-heading font-semibold">Missed</p>
                <p className="font-heading text-2xl font-bold text-on-surface">{totalQuestions - score}</p>
              </div>
              <div className="bg-surface-container-low p-4 rounded-2xl">
                <span className="material-symbols-outlined text-tertiary-fixed-dim mb-2 block">quiz</span>
                <p className="text-xs text-on-surface-variant uppercase tracking-wider font-heading font-semibold">Total</p>
                <p className="font-heading text-2xl font-bold text-on-surface">{totalQuestions}</p>
              </div>
            </div>
          </div>

          {/* Focus Areas */}
          {uniqueWeakAreas.length > 0 && (
            <div className="col-span-12 glass-card rounded-3xl p-8 border-l-4 border-primary">
              <div className="flex items-center gap-3 mb-4">
                <span className="material-symbols-outlined text-primary text-3xl">lightbulb_circle</span>
                <h3 className="font-heading text-xl font-semibold">Focus Areas to Improve</h3>
              </div>
              <div className="flex flex-wrap gap-3">
                {uniqueWeakAreas.map((topic, i) => (
                  <div key={i} className="flex items-center gap-2 bg-surface-container-low border border-primary/20 px-4 py-2 rounded-full">
                    <span className="w-2 h-2 rounded-full bg-primary motion-safe:animate-pulse"></span>
                    <span className="text-sm text-on-surface font-body">{topic}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="col-span-12 flex justify-center gap-4 mt-4">
            <button onClick={handleRestart}
              className="px-8 py-3 rounded-xl font-heading text-sm font-semibold border border-outline text-on-surface hover:bg-surface-variant/30 transition-all">
              Retry Quiz
            </button>
            <button onClick={() => navigate("/student-dashboard")}
              className="px-8 py-3 rounded-xl font-heading text-sm font-semibold bg-primary text-white shadow-lg hover:shadow-xl transition-all active:scale-95">
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (totalQuestions === 0) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <p className="font-heading text-lg text-on-surface-variant">No questions could be generated. Try a longer passage.</p>
      </div>
    );
  }

  if (!currentQuestion || !currentQuestion.options) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <p className="font-heading text-lg text-on-surface-variant">Error loading question {currentIndex + 1}. Please restart.</p>
      </div>
    );
  }

  const progress = Math.round(((currentIndex + 1) / totalQuestions) * 100);
  const progressCircumference = 2 * Math.PI * 40;
  const progressOffset = progressCircumference - (progress / 100) * progressCircumference;
  const webcamOn = canUseWebcam(profile, consent);

  return (
    <div className="max-w-[1400px] mx-auto px-4 md:px-12 py-8 animate-fade-in">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
        <div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold text-on-surface mb-1">Quiz Time</h1>
          <p className="text-base text-on-surface-variant font-body">
            Question {currentIndex + 1} of {totalQuestions}
          </p>
        </div>
        <div className="relative flex items-center justify-center">
          <svg className="w-20 h-20" viewBox="0 0 100 100" style={{transform: "rotate(-90deg)"}}>
            <circle cx="50" cy="50" r="40" fill="transparent" stroke="#e5eeff" strokeWidth="8" />
            <circle cx="50" cy="50" r="40" fill="transparent" stroke="#2a14b4" strokeWidth="8"
              strokeLinecap="round" strokeDasharray={progressCircumference} strokeDashoffset={progressOffset}
              style={{transition: "stroke-dashoffset 0.5s ease-out"}} />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-heading text-xl font-bold text-primary">{progress}%</span>
          </div>
        </div>
      </header>

      {webcamOn && (
        <div className="mb-6 max-w-xs">
          <Eye onSample={(onScreen) => focusMeterRef.current.sample(onScreen)} />
        </div>
      )}

      <div className="bento-grid">
        <QuizCard
          question={currentQuestion}
          index={currentIndex}
          total={totalQuestions}
          selectedAnswer={selectedAnswer}
          typedAnswer={typedAnswer}
          onSelect={(opt) => { qt.onInteract(); qt.onSelect(opt); setSelectedAnswer(opt); }}
          onTypedChange={(v) => { qt.onInteract(); setTypedAnswer(v); }}
          onInteract={qt.onInteract}
          onStemRefocus={qt.onStemRefocus}
          onSubmit={handleSubmit}
          showOptionsForFillBlank={showFillBlankOptions}
        />

        {/* Side: Topic + Progress */}
        <div className="col-span-12 md:col-span-4 flex flex-col gap-4">
          {currentQuestion.topic && (
            <div className="glass-card rounded-3xl p-5 border-primary/10">
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-primary" style={{fontVariationSettings: "'FILL' 1"}}>auto_awesome</span>
                <span className="font-heading text-xs font-semibold text-primary">Topic</span>
              </div>
              <p className="text-sm text-on-surface-variant font-body italic">{currentQuestion.topic}</p>
            </div>
          )}
          <div className="glass-card rounded-3xl p-5">
            <h3 className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-2">Progress</h3>
            <div className="h-2 bg-surface-variant rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
            </div>
            <p className="text-xs text-on-surface-variant mt-2 font-body">{currentIndex + 1} of {totalQuestions} completed</p>
          </div>
        </div>

        {/* Navigation */}
        <div className="col-span-12 flex justify-between items-center mt-4">
          <div></div>
          <button onClick={handleSubmit} disabled={!hasAnswer}
            className={`px-8 py-3 rounded-xl font-heading text-sm font-semibold transition-all active:scale-95 ${
              hasAnswer
                ? "bg-primary text-white shadow-lg hover:shadow-xl"
                : "bg-surface-container text-on-surface-variant cursor-not-allowed"
            }`}>
            {currentIndex === totalQuestions - 1 ? "Complete Quiz" : "Next Question"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default QuizPage;
