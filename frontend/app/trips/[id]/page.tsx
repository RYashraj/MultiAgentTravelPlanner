"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { apiFetch, ApiError } from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

function ChatPageContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tripId = params.id;

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadMessages() {
      try {
        const data = await apiFetch<Message[]>(`/trips/${tripId}/messages`);
        if (!cancelled) setMessages(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setLoadError("This trip doesn't exist or you don't have access to it.");
          } else {
            setLoadError(
              err instanceof Error ? err.message : "Couldn't load this conversation."
            );
          }
        }
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    }

    loadMessages();
    return () => {
      cancelled = true;
    };
  }, [tripId]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || isSending) return;

    const optimisticMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMessage]);
    setDraft("");
    setIsSending(true);
    setSendError(null);

    try {
      // Backend currently returns a stub reply (Week 3) until the
      // Coordinator Agent is wired up for real (Week 4+).
      const reply = await apiFetch<Message>(`/trips/${tripId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: text }),
      });
      setMessages((prev) => [...prev, reply]);
    } catch (err) {
      setSendError(
        err instanceof Error ? err.message : "Message didn't send. Try again."
      );
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans flex flex-col">
      <Navbar />

      <div className="max-w-3xl w-full mx-auto flex-1 flex flex-col px-6 py-6">
        <div className="flex items-center gap-3 mb-4">
          <Link
            href="/trips"
            className="w-8 h-8 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white hover:border-slate-700 transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Trip planning session</h2>
            <p className="text-[11px] text-slate-500 font-mono">#{tripId}</p>
          </div>
        </div>

        <div className="flex-1 rounded-2xl border border-slate-800/80 bg-slate-900/40 backdrop-blur-sm flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto px-5 py-6 space-y-4">
            {isLoadingHistory ? (
              <div className="space-y-3">
                {[0, 1].map((i) => (
                  <div
                    key={i}
                    className="h-14 w-2/3 rounded-2xl bg-slate-800/50 animate-pulse"
                  />
                ))}
              </div>
            ) : loadError ? (
              <div className="text-sm text-red-400 bg-red-950/40 border border-red-900/60 rounded-xl px-4 py-3">
                {loadError}
              </div>
            ) : messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center py-12">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 mb-4">
                  <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8-1.052 0-2.062-.14-3-.4L3 21l1.5-4.5C3.55 15.15 3 13.63 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <p className="text-sm text-slate-400 max-w-xs">
                  Tell your planning agents about this trip — dates, budget,
                  what you want to do — and they&apos;ll take it from here.
                </p>
              </div>
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                      message.role === "user"
                        ? "bg-gradient-to-r from-indigo-500 to-purple-600 text-white"
                        : "bg-slate-800/80 text-slate-200 border border-slate-700/60"
                    }`}
                  >
                    {message.content}
                  </div>
                </div>
              ))
            )}
            {isSending && (
              <div className="flex justify-start">
                <div className="bg-slate-800/80 border border-slate-700/60 rounded-2xl px-4 py-2.5 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" />
                </div>
              </div>
            )}
            <div ref={scrollAnchorRef} />
          </div>

          <form
            onSubmit={handleSend}
            className="border-t border-slate-800/80 p-3 flex items-end gap-2"
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend(e);
                }
              }}
              placeholder="Message your travel agents…"
              rows={1}
              className="flex-1 resize-none bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500/60 transition-all max-h-32"
            />
            <button
              type="submit"
              disabled={!draft.trim() || isSending}
              className="w-10 h-10 shrink-0 flex items-center justify-center bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-slate-800 disabled:to-slate-800 disabled:cursor-not-allowed rounded-xl shadow-lg shadow-indigo-500/25 transition-all"
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
              </svg>
            </button>
          </form>
          {sendError && (
            <div className="px-4 pb-3 text-xs text-red-400">{sendError}</div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function ChatPage() {
  return (
    <AuthGuard>
      <ChatPageContent />
    </AuthGuard>
  );
}
