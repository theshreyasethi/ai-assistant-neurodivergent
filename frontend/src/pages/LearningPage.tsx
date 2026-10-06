import React, { useCallback, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import api from '../services/api';
import Eye from '../components/Eye';
import type { Sentiment } from '../components/Eye';
import Chatbot from '../components/Chatbot';
import { useProfile } from '../hooks/useProfile';
import { canUseWebcam, scoringProfile } from '../types/profile';
import { earcon } from '../services/earcons';
import { speakSentences, stopSpeaking } from '../services/speech';
import { useReadingProgress } from '../hooks/useReadingProgress';
import { useVoiceCommand } from '../hooks/useVoiceCommand';
import {
  endSession, FocusMeter, getCurrentSession, setCurrentSession, startSession, track,
} from '../services/telemetry';

interface ImageDescription {
  page: number;
  name: string;
  description: string;
  degraded: boolean;
}

interface LessonState {
  text: string;
  grade_level: string | null;
  reading_difficulty: string | null;
  images: ImageDescription[];
  totalPages: number | null;
}

interface StoredLesson {
  state: LessonState;
  simplifiedText: string;
  lastSentenceIndex: number;
}

const EMPTY_STATE: LessonState = { text: '', grade_level: null, reading_difficulty: null, images: [], totalPages: null };
const LESSON_KEY_PREFIX = 'eduease.lesson.';

/** Stable, short, non-cryptographic hash — just needs the same text to
 * always map to the same contentId across sessions/devices-with-shared-
 * localStorage, so /learning/:contentId is a real, bookmarkable URL. */
function hashText(text: string): string {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = (h * 33) ^ text.charCodeAt(i);
  return (h >>> 0).toString(36);
}

function loadStoredLesson(contentId: string): StoredLesson | null {
  try {
    const raw = localStorage.getItem(LESSON_KEY_PREFIX + contentId);
    return raw ? (JSON.parse(raw) as StoredLesson) : null;
  } catch {
    return null;
  }
}
function saveStoredLesson(contentId: string, data: StoredLesson): void {
  try {
    localStorage.setItem(LESSON_KEY_PREFIX + contentId, JSON.stringify(data));
  } catch {
    /* storage full/blocked — resuming just won't work this time, lesson itself is unaffected */
  }
}

/** A queue entry is either a real lesson sentence, or an image description
 * injected at an approximate position (image.page / totalPages onto the
 * sentence array — the extracted text carries no real page-boundary
 * markers, so this is the best position information available; see
 * backend/app.py's totalPages addition to POST /upload-pdf/). */
interface QueueEntry {
  text: string;
  isImage: boolean;
}

function buildQueue(sentences: string[], images: ImageDescription[], totalPages: number | null): QueueEntry[] {
  const queue: QueueEntry[] = sentences.map((text) => ({ text, isImage: false }));
  if (!images.length || !totalPages || totalPages <= 0) return queue;

  // Insert from the back so earlier insertions don't shift later target indices.
  const withPositions = images
    .map((img) => ({ img, at: Math.min(queue.length, Math.round((img.page / totalPages) * queue.length)) }))
    .sort((a, b) => b.at - a.at);
  for (const { img, at } of withPositions) {
    queue.splice(at, 0, { text: `Image on page ${img.page}: ${img.description}`, isImage: true });
  }
  return queue;
}

const LearningPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { contentId: routeContentId } = useParams<{ contentId?: string }>();
  const { uid, profile, consent, savePrefs, loading: profileLoading } = useProfile();

  const [latestSentiment, setLatestSentiment] = React.useState<Sentiment | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatSeed, setChatSeed] = useState<string | null>(null);

  const [contentId, setContentId] = React.useState<string | null>(routeContentId ?? null);
  const [queue, setQueue] = React.useState<QueueEntry[]>([]);
  const [currentSentenceIndex, setCurrentSentenceIndex] = React.useState(0);
  const [currentWord, setCurrentWord] = React.useState<{ sentence: number; char: number } | null>(null);
  const [simplifiedText, setSimplifiedText] = React.useState<string | null>(null);
  const [highlightMode, setHighlightMode] = React.useState<'word' | 'sentence'>('sentence');
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [resumed, setResumed] = React.useState(false);

  const stopFnRef = React.useRef<() => void>(() => {});
  const replaysRef = React.useRef(0);
  const pauseCountRef = React.useRef(0);
  const wordsReadRef = React.useRef(0);
  const readingStartRef = React.useRef<number>(Date.now());
  const sessionIdRef = React.useRef<string | null>(null);
  const focusMeterRef = React.useRef(new FocusMeter());

  // ── Resolve the lesson: fresh navigation state, or resume from
  // localStorage via the URL's :contentId (e.g. after a refresh). ──
  React.useEffect(() => {
    const navState = (location.state as LessonState | undefined) ?? null;

    if (navState && navState.text) {
      const id = routeContentId || hashText(navState.text);
      setContentId(id);
      if (!routeContentId) {
        navigate(`/learning/${id}`, { replace: true, state: navState });
        return; // the navigate above re-triggers this effect with routeContentId set
      }
      const stored = loadStoredLesson(id);
      if (stored && stored.state.text === navState.text) {
        setSimplifiedText(stored.simplifiedText);
        setCurrentSentenceIndex(stored.lastSentenceIndex);
        setResumed(stored.lastSentenceIndex > 0);
      } else {
        saveStoredLesson(id, { state: navState, simplifiedText: '', lastSentenceIndex: 0 });
      }
      return;
    }

    if (routeContentId) {
      const stored = loadStoredLesson(routeContentId);
      if (stored) {
        setContentId(routeContentId);
        setSimplifiedText(stored.simplifiedText);
        setCurrentSentenceIndex(stored.lastSentenceIndex);
        setResumed(stored.lastSentenceIndex > 0);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeContentId]);

  const lessonState: LessonState = (location.state as LessonState | undefined) ?? EMPTY_STATE;
  const effectiveText = lessonState.text || (contentId ? loadStoredLesson(contentId)?.state.text ?? '' : '');

  // ── Simplify (skip the API call entirely if we already have it cached). ──
  React.useEffect(() => {
    if (!effectiveText || profileLoading || simplifiedText) return;
    api
      .post('/simplify-text/', {
        text: effectiveText,
        grade_level: lessonState.grade_level ?? null,
        reading_difficulty: lessonState.reading_difficulty ?? null,
        profile: scoringProfile(profile),
      })
      .then((response) => {
        const simplified = response.data.simplified_text;
        setSimplifiedText(simplified);
        if (contentId) {
          saveStoredLesson(contentId, {
            state: { ...lessonState, text: effectiveText },
            simplifiedText: simplified,
            lastSentenceIndex: 0,
          });
        }
      })
      .catch((error) => console.error('Error simplifying text:', error));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveText, profileLoading, contentId]);

  React.useEffect(() => {
    if (!simplifiedText) return;
    const sentences = simplifiedText.split(/(?<=[.!?])\s+/).map((s: string) => s.trim()).filter(Boolean);
    setQueue(buildQueue(sentences, lessonState.images || [], lessonState.totalPages ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simplifiedText]);

  // Persist reading position for resumability, every time it changes.
  React.useEffect(() => {
    if (!contentId || !simplifiedText) return;
    saveStoredLesson(contentId, {
      state: { ...lessonState, text: effectiveText },
      simplifiedText,
      lastSentenceIndex: currentSentenceIndex,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentId, currentSentenceIndex, simplifiedText]);

  // ── Telemetry: a reading session, registered globally so VoiceNavigator
  // can attribute voice commands to it (roadmap task P2-04). ──
  React.useEffect(() => {
    if (profileLoading || !uid || !contentId || sessionIdRef.current) return;
    let cancelled = false;
    startSession(uid, 'reading', contentId).then((id) => {
      if (cancelled) return;
      sessionIdRef.current = id;
      if (id) setCurrentSession(id);
      readingStartRef.current = Date.now();
    });
    return () => {
      cancelled = true;
    };
  }, [profileLoading, uid, contentId]);

  const flushReadingTelemetry = useCallback(
    (ttsUsed: boolean) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || !uid) return;
      const { focusRatio, focusSamples } = focusMeterRef.current.read();
      track({
        type: 'reading',
        sessionId,
        studentId: uid,
        ts: Date.now(),
        contentId,
        wordsRead: wordsReadRef.current,
        wpmSetting: Math.round((profile.prefs.ttsRate || 1) * 200),
        elapsedMs: Date.now() - readingStartRef.current,
        replays: replaysRef.current,
        ttsUsed,
        pauseCount: pauseCountRef.current,
        focusRatio,
        focusSamples,
        simplifyProfile: scoringProfile(profile),
      });
    },
    [contentId, profile, uid],
  );

  React.useEffect(() => {
    return () => {
      flushReadingTelemetry(isPlaying);
      if (sessionIdRef.current) {
        void endSession(sessionIdRef.current, {
          totalQuestions: 0, correct: 0, totalTimeMs: Date.now() - readingStartRef.current,
          completed: false, meanFocusRatio: focusMeterRef.current.read().focusRatio,
        });
        setCurrentSession(null);
      }
      stopFnRef.current();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-start when the student has voice-first or "read aloud
  // automatically" on, once content is actually ready.
  React.useEffect(() => {
    if (simplifiedText && !profileLoading && (profile.prefs.voiceFirst || profile.prefs.ttsEnabled) && !resumed) {
      setIsPlaying(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simplifiedText, profileLoading]);

  const totalEntries = queue.length;
  const { announceNow } = useReadingProgress(currentSentenceIndex, totalEntries, { voiceFirst: profile.prefs.voiceFirst });

  // ── Playback ──
  const speakFrom = useCallback(
    (startIndex: number, playThrough: boolean) => {
      stopFnRef.current();
      if (!queue.length) return;
      const toSpeak = playThrough ? queue.slice(startIndex) : [queue[startIndex]];
      if (!toSpeak.length) return;

      if (playThrough && profile.prefs.voiceFirst && queue[startIndex]?.isImage) earcon.content();

      stopFnRef.current = speakSentences(
        toSpeak.map((e) => e.text),
        {
          rate: profile.prefs.ttsRate || 1,
          lang: profile.prefs.speechLang,
          onSentenceStart: (i) => {
            const idx = startIndex + i;
            setCurrentSentenceIndex(idx);
            setCurrentWord(null);
            wordsReadRef.current += (queue[idx]?.text.split(/\s+/).length || 0);
          },
          onWordBoundary: (i, charIndex) => setCurrentWord({ sentence: startIndex + i, char: charIndex }),
          onDone: () => {
            if (playThrough) setIsPlaying(false);
          },
        },
      );
    },
    [queue, profile.prefs.ttsRate, profile.prefs.speechLang, profile.prefs.voiceFirst],
  );

  React.useEffect(() => {
    if (isPlaying) {
      speakFrom(currentSentenceIndex, true);
    } else {
      stopFnRef.current();
    }
    // Deliberately only re-run on isPlaying toggling, not on every
    // sentence index change — speakFrom's own onSentenceStart advances
    // currentSentenceIndex WHILE already playing, and re-triggering this
    // effect on that change would restart the queue from the same sentence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying]);

  const handlePlayPause = () => {
    if (isPlaying) pauseCountRef.current += 1;
    setIsPlaying((p) => !p);
  };

  const handleReset = () => {
    stopFnRef.current();
    setIsPlaying(false);
    setCurrentSentenceIndex(0);
    setCurrentWord(null);
  };

  const handleRepeat = useCallback(() => {
    replaysRef.current += 1;
    // If playback was running, "repeat" means replay this sentence and
    // keep going (playThrough=true from the current index naturally
    // includes replaying it first) — passing false here would speak the
    // one sentence, stop, and leave isPlaying stuck at true with nothing
    // actually playing. If paused, it means just this one sentence.
    speakFrom(currentSentenceIndex, isPlaying);
  }, [currentSentenceIndex, isPlaying, speakFrom]);

  const handleNext = useCallback(() => {
    const next = Math.min(currentSentenceIndex + 1, Math.max(totalEntries - 1, 0));
    setCurrentSentenceIndex(next);
    speakFrom(next, isPlaying);
  }, [currentSentenceIndex, totalEntries, isPlaying, speakFrom]);

  const handlePrevious = useCallback(() => {
    const prev = Math.max(currentSentenceIndex - 1, 0);
    setCurrentSentenceIndex(prev);
    speakFrom(prev, isPlaying);
  }, [currentSentenceIndex, isPlaying, speakFrom]);

  // ── Voice commands (roadmap task P2-04/P2-06) ──
  useVoiceCommand('READ_NEXT', handleNext);
  useVoiceCommand('READ_PREVIOUS', handlePrevious);
  useVoiceCommand('READ_ALL', () => { setIsPlaying(true); speakFrom(currentSentenceIndex, true); });
  useVoiceCommand('REPEAT', handleRepeat);
  useVoiceCommand('PROGRESS', announceNow);
  useVoiceCommand('FASTER', () => void savePrefs({ ttsRate: Math.min(2, (profile.prefs.ttsRate || 1) + 0.1) }));
  useVoiceCommand('SLOWER', () => void savePrefs({ ttsRate: Math.max(0.5, (profile.prefs.ttsRate || 1) - 0.1) }));
  useVoiceCommand('EXPLAIN', () => {
    setChatSeed(`Please explain this in simpler words: "${queue[currentSentenceIndex]?.text ?? ''}"`);
    setChatOpen(true);
  });

  const navigateToQuiz = useCallback(() => {
    if (simplifiedText) navigate('/quiz', { state: { text: simplifiedText } });
  }, [navigate, simplifiedText]);

  const currentEntry = queue[currentSentenceIndex];
  const progressPct = totalEntries > 0 ? Math.round(((currentSentenceIndex + 1) / totalEntries) * 100) : 0;

  const renderContent = () => {
    if (!simplifiedText) return <p className="text-slate-500" role="status">Loading content...</p>;
    if (!currentEntry) return <p className="text-slate-500" role="status">No content to read.</p>;

    if (currentEntry.isImage) {
      return (
        <div className="text-xl sm:text-2xl font-semibold mb-6 leading-relaxed tracking-wide flex items-start gap-3">
          <span className="material-symbols-outlined text-primary text-3xl shrink-0" aria-hidden="true">image</span>
          <span aria-label={currentEntry.text}>{currentEntry.text}</span>
        </div>
      );
    }

    if (highlightMode === 'word') {
      const words = currentEntry.text.split(' ');
      let offset = 0;
      return (
        <div
          className="text-3xl sm:text-4xl font-semibold mb-6 min-h-[2.5rem] leading-snug tracking-wide"
          aria-label={`Sentence ${currentSentenceIndex + 1} of ${totalEntries}`}
        >
          {words.map((word, idx) => {
            const start = offset;
            offset += word.length + 1;
            const isCurrent = currentWord?.sentence === currentSentenceIndex && currentWord.char === start;
            return (
              <span key={idx} aria-current={isCurrent ? 'true' : undefined} className={isCurrent ? 'bg-amber-200 px-2 rounded-md shadow-sm' : ''}>
                {word}{' '}
              </span>
            );
          })}
        </div>
      );
    }

    return (
      <div
        className="text-xl sm:text-2xl font-semibold mb-6 leading-relaxed tracking-wide"
        aria-label={`Sentence ${currentSentenceIndex + 1} of ${totalEntries}`}
      >
        <span className="bg-emerald-200/70 px-2 rounded-md shadow-sm">{currentEntry.text}</span>
      </div>
    );
  };

  const webcamOn = canUseWebcam(profile, consent);

  return (
    <>
      <div className="relative animate-fade-in flex flex-col lg:flex-row gap-6">
        {/* Focus Tracker — never mounted for blind/low-vision or without consent (roadmap task P2-09) */}
        <div className="w-full lg:w-1/3 flex flex-col gap-6">
          {webcamOn && (
            <Eye
              sentiment={latestSentiment}
              onFocusChange={(isFocused) => {
                focusMeterRef.current.set(isFocused);
                if (!isFocused && isPlaying) setIsPlaying(false);
              }}
            />
          )}
          {/* Progress card */}
          <div className="glass-card rounded-[2rem] p-5 flex flex-col gap-3">
            <div className="flex justify-between items-center">
              <span className="font-heading text-xs font-semibold text-on-surface-variant uppercase tracking-widest">Reading Progress</span>
              <span className="font-heading text-xs font-bold text-tertiary-fixed-dim">{progressPct}%</span>
            </div>
            <div className="w-full h-3 bg-surface-container-high rounded-full overflow-hidden">
              <div className="h-full bg-tertiary-fixed-dim rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }}></div>
            </div>
            {resumed && <p className="text-xs text-on-surface-variant font-body">Resumed where you left off.</p>}
          </div>
        </div>

        {/* Reading Module */}
        <div className="flex-1 glass-card rounded-[2rem] overflow-hidden flex flex-col shadow-2xl relative">
          <header className="p-4 md:p-5 border-b border-white/20 bg-surface-container-lowest/50 backdrop-blur-md flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2 bg-surface-container rounded-full px-3 py-1.5">
                <span className="material-symbols-outlined text-on-surface-variant text-[18px]">ink_highlighter</span>
                <label className="sr-only" htmlFor="highlight-mode">Highlight mode</label>
                <select id="highlight-mode" value={highlightMode}
                  onChange={(e) => setHighlightMode(e.target.value as 'word' | 'sentence')}
                  className="bg-transparent border-none focus:ring-0 text-xs font-heading font-semibold text-on-surface cursor-pointer">
                  <option value="sentence">Sentence</option>
                  <option value="word">Word</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={handlePrevious} aria-label="Previous sentence"
                className="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant hover:bg-primary-container hover:text-on-primary transition-all">
                <span className="material-symbols-outlined">skip_previous</span>
              </button>
              <button onClick={handlePlayPause} aria-label={isPlaying ? 'Pause' : 'Play'}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-primary text-on-primary shadow-lg hover:scale-105 active:scale-95 transition-all">
                <span className="material-symbols-outlined">{isPlaying ? 'pause' : 'play_arrow'}</span>
              </button>
              <button onClick={handleNext} aria-label="Next sentence"
                className="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant hover:bg-primary-container hover:text-on-primary transition-all">
                <span className="material-symbols-outlined">skip_next</span>
              </button>
            </div>
          </header>

          <article id="reading-area" role="region" aria-label="Reading area" aria-live="polite" aria-atomic="false"
            className="flex-1 overflow-y-auto p-8 md:p-10 scroll-smooth">
            <div className="max-w-2xl mx-auto">{renderContent()}</div>
          </article>

          <footer className="p-4 md:p-5 border-t border-white/20 flex justify-between items-center bg-surface-bright/80 backdrop-blur-md">
            <button onClick={handleReset}
              className="flex items-center gap-1.5 font-heading text-xs font-semibold text-on-surface-variant hover:text-primary transition-colors">
              <span className="material-symbols-outlined text-[18px]">restart_alt</span>
              Reset
            </button>
            <button onClick={navigateToQuiz}
              className="px-5 py-2.5 rounded-xl bg-primary text-on-primary font-heading text-xs font-semibold shadow-md hover:shadow-lg transition-all active:scale-95">
              Take Quiz
            </button>
          </footer>
        </div>
      </div>

      <button
        onClick={() => setChatOpen((prev) => !prev)}
        aria-label={chatOpen ? 'Close assistant' : 'Open assistant'}
        className="fixed bottom-4 right-4 z-[9999] w-14 h-14 rounded-full bg-primary text-on-primary shadow-2xl flex items-center justify-center hover:scale-110 active:scale-95 transition-all group"
        style={{isolation: "isolate"}}
      >
        <span className="material-symbols-outlined group-hover:rotate-12 transition-transform">{chatOpen ? 'close' : 'auto_awesome'}</span>
      </button>

      {chatOpen && (
        <Chatbot
          onSentiment={setLatestSentiment}
          gradeLevel={lessonState.grade_level}
          readingDifficulty={lessonState.reading_difficulty}
          seedMessage={chatSeed}
          onSeedConsumed={() => setChatSeed(null)}
          onClose={() => setChatOpen(false)}
        />
      )}
    </>
  );
};

export default LearningPage;
