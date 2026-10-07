import React from 'react';
import { Link } from 'react-router-dom';
import Chatbot from '../components/Chatbot';
import VoiceEssay from '../components/VoiceEssay';
import { useProfile } from '../hooks/useProfile';
import { scoringProfile } from '../types/profile';
import { endSession, setCurrentSession, startSession, track, triggerEvaluation } from '../services/telemetry';
import { useTranslation } from 'react-i18next';

const DashboardPage: React.FC = () => {
  const [showChatbot, setShowChatbot] = React.useState(false);
  const [showWritingPractice, setShowWritingPractice] = React.useState(false);
  const { t, i18n } = useTranslation();
  const { uid, profile } = useProfile();
  const writingSessionRef = React.useRef<string | null>(null);

  const openWritingPractice = async () => {
    setShowWritingPractice(true);
    if (uid) {
      const id = await startSession(uid, 'quiz');
      writingSessionRef.current = id;
      if (id) setCurrentSession(id);
    }
  };

  const onEssayScored = (result: { know: number | null; expr: number | null }) => {
    const sessionId = writingSessionRef.current;
    if (!sessionId || !uid) return;
    track({
      type: 'question', sessionId, studentId: uid, ts: Date.now(),
      questionId: 'writing-practice', conceptId: null, topic: 'Writing practice', difficulty: 3,
      questionType: 'short_answer', itemKind: null, selected: null,
      correct: (result.know ?? 0) >= 0.5, timeMs: 0, timeToFirstInteractionMs: null,
      attempts: 1, answerChanges: 0, hintsUsed: 0, revisits: 0, reRead: false,
      focusRatio: null, focusSamples: 0, isRepresentation: false, originalQuestionId: null,
      classification: null, classifierVersion: null, degraded: false,
      know: result.know, expr: result.expr, blurCount: 0,
    });
    void endSession(sessionId, {
      totalQuestions: 1, correct: (result.know ?? 0) >= 0.5 ? 1 : 0, totalTimeMs: 0,
      completed: true, meanFocusRatio: null,
    }).then(() => triggerEvaluation(sessionId, uid, scoringProfile(profile)));
  };

  const changeLanguage = (lng: string) => i18n.changeLanguage(lng);

  const cards = [
    {
      to: "/upload",
      icon: "upload_file",
      title: t('Upload a PDF to get started'),
      desc: t('Generate simplified content & quizzes'),
      isHero: true,
    },
    {
      to: "/content",
      icon: "library_books",
      title: t('Manage Content'),
      desc: t('View and organize learning material'),
      isHero: true,
    },
    {
      to: "/learning",
      icon: "menu_book",
      title: t('Start Learning'),
      desc: t('Guided reading with focus tracking'),
      isHero: true,
    },
  ];

  return (
    <>
      <div className="space-y-8 animate-fade-in">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <span className="font-heading text-xs font-semibold text-primary uppercase tracking-widest">{t('Student Dashboard')}</span>
            <h1 className="font-heading text-3xl md:text-4xl font-bold text-on-surface mt-1">{t('Welcome to your dashboard!')}</h1>
          </div>
          <div className="glass-card rounded-full px-1 py-0.5 flex">
            {["en", "hi", "ta"].map((lng) => (
              <button key={lng} onClick={() => changeLanguage(lng)}
                className={`px-3 py-1.5 text-xs font-heading font-semibold rounded-full transition-all ${
                  i18n.language === lng ? "bg-primary text-white" : "text-on-surface-variant hover:text-primary"
                }`}>
                {lng.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Bento Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {cards.map((card) => (
            <Link key={card.to} to={card.to}
              className="bg-primary-container text-white group relative rounded-3xl p-8 min-h-[280px] flex flex-col justify-between overflow-hidden shadow-md hover:shadow-xl transition-all hover:-translate-y-1">
              <div className="z-10">
                <span className="material-symbols-outlined text-4xl mb-4 block text-white/90"
                  style={{fontVariationSettings: "'FILL' 1"}}>{card.icon}</span>
                <h3 className="font-heading text-xl font-bold mb-2 text-white">{card.title}</h3>
                <p className="text-sm font-body leading-relaxed text-indigo-100">{card.desc}</p>
              </div>
              <div className="flex items-center gap-1 mt-4 z-10 text-white/90">
                <span className="font-heading text-xs font-semibold">Open</span>
                <span className="material-symbols-outlined text-[16px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </div>
              <div className="absolute -right-8 -bottom-8 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-[160px]" style={{fontVariationSettings: "'FILL' 1"}}>{card.icon}</span>
              </div>
            </Link>
          ))}
        </div>

        {/* Dysgraphia writing practice (roadmap P4-09) — reachable entry
            point for VoiceEssay, scoped to the profile it supports. */}
        {profile.disabilities.includes('dysgraphia') && (
          <button
            type="button"
            onClick={openWritingPractice}
            className="w-full glass-card rounded-3xl p-6 flex items-center gap-4 text-left hover:shadow-lg transition-all"
          >
            <span className="material-symbols-outlined text-3xl text-primary" aria-hidden="true">mic</span>
            <span>
              <span className="block font-heading text-lg font-semibold text-on-surface">Practice writing by voice</span>
              <span className="block text-sm text-on-surface-variant font-body">
                Say your answer out loud — we'll organize it into a structured essay for you.
              </span>
            </span>
          </button>
        )}
      </div>

      {showWritingPractice && (
        <div
          role="dialog"
          aria-label="Writing practice"
          className="fixed inset-0 z-[200] bg-black/40 flex items-center justify-center p-4"
        >
          <div className="max-w-2xl w-full max-h-[90vh] overflow-y-auto relative">
            <button
              type="button"
              onClick={() => setShowWritingPractice(false)}
              aria-label="Close writing practice"
              className="absolute -top-3 -right-3 w-9 h-9 rounded-full bg-white shadow-lg flex items-center justify-center z-10"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
            <VoiceEssay
              prompt="Tell me about something you learned recently."
              onScored={onEssayScored}
            />
          </div>
        </div>
      )}

      {/* Chatbot FAB — rendered outside page content flow */}
      <div className="fixed bottom-4 right-4 z-[9999] flex items-end gap-3 pointer-events-auto" style={{isolation: "isolate"}}>
        {!showChatbot && (
          <div className="bg-white rounded-2xl px-4 py-2.5 shadow-xl border border-outline-variant/20 max-w-[200px] animate-fade-in">
            <p className="text-xs font-heading font-semibold text-on-surface">Ask me anything!</p>
            <p className="text-[10px] text-on-surface-variant font-body mt-0.5">I am your AI learning assistant</p>
          </div>
        )}
        <button onClick={() => setShowChatbot(!showChatbot)}
          className="w-14 h-14 bg-primary text-on-primary rounded-full shadow-2xl flex items-center justify-center hover:scale-110 active:scale-95 transition-all group flex-shrink-0">
          <span className="material-symbols-outlined group-hover:rotate-12 transition-transform">
            {showChatbot ? "close" : "auto_awesome"}
          </span>
        </button>
      </div>

      {showChatbot && <Chatbot onClose={() => setShowChatbot(false)} />}
    </>
  );
};

export default DashboardPage;
