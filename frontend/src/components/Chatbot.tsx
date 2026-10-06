import React, { useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';
import { auth } from '../services/firebase';
import { useProfile } from '../hooks/useProfile';
import { scoringProfile } from '../types/profile';
import { earcon } from '../services/earcons';
import { speakOnce, stopSpeaking } from '../services/speech';
import { isSttSupported, listenOnce } from '../services/stt';
import type { Sentiment } from './Eye';

interface Message {
  text: string;
  sender: 'user' | 'bot';
}

interface ChatbotProps {
  onSentiment?: (sentiment: Sentiment) => void;
  gradeLevel?: string | null;
  readingDifficulty?: string | null;
  /** A message to send automatically on open — e.g. the voice EXPLAIN
   * command seeds "explain this: <sentence>" (LearningPage.tsx). */
  seedMessage?: string | null;
  onSeedConsumed?: () => void;
  onClose?: () => void;
}

const Chatbot: React.FC<ChatbotProps> = ({ onSentiment, gradeLevel, readingDifficulty, seedMessage, onSeedConsumed, onClose }) => {
  const { profile } = useProfile();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const sessionId = useMemo(() => {
    const uid = auth.currentUser?.uid ?? 'anon';
    return `${uid}_${Date.now()}`;
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus trap + initial focus on the input, Escape as barge-in (stop
  // speech) or close, Tab wraps within the dialog.
  useEffect(() => {
    inputRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (window.speechSynthesis?.speaking) {
          stopSpeaking();
          return;
        }
        onClose?.();
        return;
      }
      if (e.key !== 'Tab' || !dialogRef.current) return;
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>('button, input, [tabindex]:not([tabindex="-1"])');
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { text, sender: 'user' }]);
    setInput('');
    setLoading(true);
    try {
      const response = await api.post('/chatbot/', {
        text,
        session_id: sessionId,
        grade_level: gradeLevel ?? null,
        reading_difficulty: readingDifficulty ?? null,
        profile: scoringProfile(profile) !== 'default' ? scoringProfile(profile) : null,
      });
      const reply = response.data?.response || response.data?.reply || "I'm not sure how to respond to that.";
      setMessages((prev) => [...prev, { text: reply, sender: 'bot' }]);
      if (response.data?.sentiment && onSentiment) onSentiment(response.data.sentiment);
      if (profile.prefs.voiceFirst || profile.prefs.ttsEnabled) {
        speakOnce(reply, { rate: profile.prefs.ttsRate || 1, lang: profile.prefs.speechLang });
      }
    } catch (error: any) {
      const fallback = error?.response?.data?.detail || 'Sorry, I am having trouble connecting right now.';
      setMessages((prev) => [...prev, { text: fallback, sender: 'bot' }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (seedMessage) {
      void sendMessage(seedMessage);
      onSeedConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedMessage]);

  const handleSend = () => void sendMessage(input);

  const handleMic = () => {
    if (!isSttSupported()) {
      speakOnce('Voice input is not supported in this browser.');
      return;
    }
    setListening(true);
    earcon.micOpen();
    listenOnce(profile.prefs.speechLang)
      .then(({ transcript }) => {
        if (transcript) void sendMessage(transcript);
      })
      .catch(() => earcon.notUnderstood())
      .finally(() => setListening(false));
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="chatbot-title"
      className="fixed bottom-24 right-4 w-96 max-w-[calc(100vw-2rem)] max-h-[500px] z-[9998] flex flex-col bg-white rounded-3xl shadow-2xl border border-white/20 overflow-hidden animate-fade-in"
    >
      {/* Header */}
      <div className="bg-gradient-to-r from-primary to-primary-container p-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center">
          <span className="material-symbols-outlined text-white text-[20px]" style={{fontVariationSettings: "'FILL' 1"}}>auto_awesome</span>
        </div>
        <div>
          <p id="chatbot-title" className="font-heading text-sm font-semibold text-white">EduEase Assistant</p>
          <p className="text-[10px] text-white/70 font-body">AI-powered learning support</p>
        </div>
      </div>

      {/* Messages — role="log" so a screen reader treats new entries as a
          running conversation, not a one-shot alert. */}
      <div role="log" aria-live="polite" aria-atomic="false" className="flex-1 overflow-y-auto p-4 space-y-3 bg-surface-bright min-h-[200px] max-h-[340px]">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <span className="material-symbols-outlined text-4xl text-primary/20 block mb-2" style={{fontVariationSettings: "'FILL' 1"}}>chat_bubble</span>
            <p className="text-xs text-on-surface-variant font-body">Ask me anything about your reading material, by typing or by voice.</p>
          </div>
        )}
        {messages.map((msg, index) => (
          <div key={index} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <span className="sr-only">{msg.sender === 'user' ? 'You said: ' : 'Assistant replied: '}</span>
            <div className={`max-w-[80%] px-4 py-2.5 text-sm font-body leading-relaxed ${
              msg.sender === 'user'
                ? 'bg-primary text-white rounded-2xl rounded-br-md'
                : 'bg-surface-container text-on-surface rounded-2xl rounded-bl-md'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start" role="status" aria-label="Assistant is thinking">
            <div className="bg-surface-container text-on-surface-variant rounded-2xl rounded-bl-md px-4 py-2.5 text-sm font-body">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce" style={{animationDelay: "0ms"}}></span>
                <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce" style={{animationDelay: "150ms"}}></span>
                <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce" style={{animationDelay: "300ms"}}></span>
              </span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-outline-variant/20 bg-white">
        <div className="flex items-center gap-2 bg-surface-container-low rounded-xl px-3 py-1 border border-outline-variant/30 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-all">
          <label htmlFor="chatbot-input" className="sr-only">Type your message</label>
          <input
            ref={inputRef}
            id="chatbot-input"
            type="text"
            className="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none text-sm font-body text-on-surface placeholder:text-on-surface-variant/50 py-2"
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !loading) handleSend();
            }}
            disabled={loading}
          />
          <button
            type="button"
            onClick={handleMic}
            aria-label={listening ? 'Listening for your question' : 'Ask by voice'}
            aria-pressed={listening}
            className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
              listening ? 'bg-error text-on-error motion-safe:animate-pulse' : 'bg-surface-container text-on-surface-variant hover:bg-primary-container hover:text-on-primary'
            }`}
          >
            <span className="material-symbols-outlined text-[18px]">{listening ? 'mic' : 'mic_none'}</span>
          </button>
          <button
            className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
              input.trim() ? 'bg-primary text-white hover:bg-primary-container active:scale-95' : 'bg-surface-container text-on-surface-variant'
            }`}
            onClick={handleSend}
            disabled={loading || !input.trim()}
            aria-label="Send message"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default Chatbot;
