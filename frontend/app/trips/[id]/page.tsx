"use client";

import { useEffect, useState, useRef, FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { getSessionToken, signOut } from "@/lib/supabase";
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { LogOut, Send, Terminal, Calendar, Loader, Compass, ChevronLeft, CheckCircle } from "lucide-react";

type Message = {
  id: string;
  sender: string;
  content: string;
  created_at: string;
  isStreaming?: boolean;
};

type Itinerary = {
  id: string;
  day_number: number;
  title: string;
  description: string;
  activities?: any;
};

type Trip = {
  id: string;
  destination: string;
  status: string;
  created_at: string;
};

function ChatPageContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tripId = params.id;

  const [trip, setTrip] = useState<Trip | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [itineraries, setItineraries] = useState<Itinerary[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [itinerariesLoading, setItinerariesLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [inputMessage, setInputMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [activeLogs, setActiveLogs] = useState<string[]>([]);
  const [sendError, setSendError] = useState<string | null>(null);

  // Tabs for Workspace detail panel
  const [activeTab, setActiveTab] = useState<"chat" | "console">("chat");

  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  // 1. Fetch Trip details and Messages History
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      try {
        setIsLoadingHistory(true);
        // Find destination name by scanning all user trips
        const tripsData = await apiFetch<Trip[]>("/trips");
        const currentTrip = tripsData.find((t) => t.id === tripId);
        if (currentTrip) {
          if (!cancelled) setTrip(currentTrip);
        } else {
          throw new Error("Trip not found or access denied.");
        }

        const messagesData = await apiFetch<Message[]>(`/trips/${tripId}/messages`);
        if (!cancelled) setMessages(messagesData);
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Couldn't load trip details.");
        }
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    }

    loadData();
    fetchItineraries();

    return () => {
      cancelled = true;
    };
  }, [tripId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchItineraries = async () => {
    try {
      setItinerariesLoading(true);
      const data = await apiFetch<Itinerary[]>(`/trips/${tripId}/itineraries`);
      setItineraries(data);
    } catch (err) {
      console.error("Failed to load itineraries:", err);
    } finally {
      setItinerariesLoading(false);
    }
  };

  const handleSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    const userText = inputMessage.trim();
    setInputMessage("");
    setIsSending(true);
    setSendError(null);
    setActiveLogs([]);

    // Optimistically add user bubble
    const tempUserMsg: Message = {
      id: `local-user-${Date.now()}`,
      sender: "user",
      content: userText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    const assistantMsgId = `local-assistant-${Date.now()}`;
    const token = getSessionToken();

    try {
      // Connect to SSE streaming endpoint
      const response = await fetch(`${API_BASE_URL}/trips/${tripId}/messages?stream=true`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: userText }),
      });

      if (!response.ok) {
        throw new Error("Failed to reach planning agents.");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No stream reader available");

      let buffer = "";
      let tempAssistantContent = "";

      // Append assistant placeholder bubble
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          sender: "assistant",
          content: "",
          created_at: new Date().toISOString(),
          isStreaming: true,
        },
      ]);

      // Focus console log tab automatically on message send
      setActiveTab("console");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.trim()) continue;

          const lines = part.split("\n");
          let eventType = "";
          let dataStr = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.substring(7).trim();
            } else if (line.startsWith("data: ")) {
              dataStr = line.substring(6).trim();
            }
          }

          if (eventType && dataStr) {
            try {
              const data = JSON.parse(dataStr);
              if (eventType === "user_message") {
                // Swap temp user message
                setMessages((prev) =>
                  prev.map((msg) => (msg.id.startsWith("local-user-") ? data : msg))
                );
              } else if (eventType === "agent_log") {
                // Record sub-agent logs
                setActiveLogs((prev) => [...prev, `[${data.agent}] ${data.content}`]);
              } else if (eventType === "message_chunk") {
                // Append chunk
                tempAssistantContent += data.content;
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: tempAssistantContent }
                      : msg
                  )
                );
              } else if (eventType === "message_complete") {
                // Finalize assistant message bubble
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { id: data.id, sender: "assistant", content: data.content, created_at: data.created_at }
                      : msg
                  )
                );
                // Refresh itineraries
                fetchItineraries();
                // Switch back to chat bubble view
                setActiveTab("chat");
              }
            } catch (pErr) {
              console.error("Failed to parse SSE payload", pErr);
            }
          }
        }
      }
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "An error occurred.");
      // Remove placeholder bubble on error
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans flex flex-col">
      <Navbar />

      <div className="max-w-7xl w-full mx-auto px-6 py-6 flex-1 flex flex-col space-y-4">
        
        {/* Navigation / Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/trips"
              className="w-9 h-9 rounded-xl bg-slate-900 border border-slate-800/80 flex items-center justify-center text-slate-400 hover:text-white hover:border-slate-700 transition-all"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <div>
              <h2 className="text-md font-bold text-white">
                {trip ? `Trip to ${trip.destination}` : "Planning Workspace"}
              </h2>
              <p className="text-[10px] text-slate-500 font-mono">ID: {tripId}</p>
            </div>
          </div>
        </div>

        {loadError ? (
          <div className="text-sm text-red-400 bg-red-950/40 border border-red-900/60 rounded-2xl px-4 py-3">
            {loadError}
          </div>
        ) : (
          /* Main Workspace Split Layout */
          <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
            
            {/* Left & Middle Column: Interactive Workspace */}
            <div className="lg:col-span-2 flex flex-col border border-slate-800/80 bg-slate-900/40 rounded-3xl overflow-hidden backdrop-blur-sm relative">
              
              {/* Tab Selector */}
              <div className="flex border-b border-slate-850 px-4 bg-slate-950/20 items-center justify-between shrink-0 select-none">
                <div className="flex gap-2 py-2">
                  <button
                    onClick={() => setActiveTab("chat")}
                    className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                      activeTab === "chat"
                        ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Chat Workspace
                  </button>
                  <button
                    onClick={() => setActiveTab("console")}
                    className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 ${
                      activeTab === "console"
                        ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Terminal className="w-3.5 h-3.5" /> Agent Console
                    {isSending && (
                      <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                    )}
                  </button>
                </div>
              </div>

              {/* Workspace Content Panels */}
              <div className="flex-1 overflow-y-auto p-6 min-h-[350px]">
                {activeTab === "chat" ? (
                  /* Chat Bubbles View */
                  <div className="space-y-4">
                    {isLoadingHistory ? (
                      <div className="space-y-3">
                        <div className="h-16 w-3/4 rounded-2xl bg-slate-800/40 animate-pulse" />
                        <div className="h-20 w-1/2 rounded-2xl bg-slate-800/40 animate-pulse" />
                      </div>
                    ) : messages.length === 0 ? (
                      <div className="h-full flex flex-col items-center justify-center text-center py-16">
                        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 mb-4 animate-bounce">
                          <Compass className="w-6 h-6 text-white" />
                        </div>
                        <p className="text-sm text-slate-400 max-w-xs leading-relaxed">
                          Say hi to your crew! Tell them where you want to go, your dates, or what budget constraints you have.
                        </p>
                      </div>
                    ) : (
                      messages.map((message) => (
                        <div
                          key={message.id}
                          className={`flex ${
                            message.sender === "user" ? "justify-end" : "justify-start"
                          }`}
                        >
                          <div
                            className={`max-w-[80%] rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                              message.sender === "user"
                                ? "bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-950/20"
                                : "bg-slate-900/80 border border-slate-800/70 text-slate-200"
                            }`}
                          >
                            {message.content}
                          </div>
                        </div>
                      ))
                    )}
                    <div ref={scrollAnchorRef} />
                  </div>
                ) : (
                  /* Agent Console Log Terminal */
                  <div className="font-mono text-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-850 pb-2 mb-3 text-slate-500 select-none">
                      <span>agent_trace_logs.sh</span>
                      {isSending && (
                        <span className="flex items-center gap-1.5 text-indigo-400 font-semibold animate-pulse">
                          <Loader className="w-3.5 h-3.5 animate-spin" /> Stream Active
                        </span>
                      )}
                    </div>
                    
                    {activeLogs.length === 0 ? (
                      <div className="text-slate-600 italic">No console logs recorded in this session yet. Send a message to start orchestration.</div>
                    ) : (
                      <div className="space-y-2">
                        {activeLogs.map((log, idx) => (
                          <div key={idx} className="flex gap-2">
                            <span className="text-slate-600 select-none">&gt;</span>
                            <span className={log.includes("✔") || log.includes("success") ? "text-emerald-400" : "text-slate-300"}>
                              {log}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Form Input Area */}
              <form
                onSubmit={handleSend}
                className="border-t border-slate-850 p-4 bg-slate-950/10 flex items-end gap-3 shrink-0"
              >
                <textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend(e);
                    }
                  }}
                  placeholder="Tell your planning agents about your trip details..."
                  rows={1}
                  className="flex-1 resize-none bg-slate-950/80 border border-slate-850 rounded-2xl px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500/60 transition-all max-h-32 font-sans"
                />
                <button
                  type="submit"
                  disabled={!inputMessage.trim() || isSending}
                  className="w-11 h-11 shrink-0 flex items-center justify-center bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-slate-850 disabled:to-slate-850 disabled:cursor-not-allowed rounded-2xl shadow-lg shadow-indigo-500/20 transition-all"
                >
                  <Send className="w-4 h-4 text-white" />
                </button>
              </form>
              {sendError && (
                <div className="px-6 pb-4 text-xs text-red-400 bg-slate-950/15">{sendError}</div>
              )}
            </div>

            {/* Right Column: Compiled Itineraries Display */}
            <aside className="border border-slate-800/80 bg-slate-900/40 rounded-3xl p-6 flex flex-col space-y-4 backdrop-blur-sm">
              <div className="flex items-center gap-2.5 text-xs font-bold text-slate-400 uppercase tracking-widest border-b border-slate-850 pb-3 select-none shrink-0">
                <Calendar className="w-4 h-4 text-indigo-400" />
                <span>Generated Itineraries</span>
              </div>

              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {itinerariesLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader className="w-6 h-6 text-indigo-400 animate-spin" />
                  </div>
                ) : itineraries.length === 0 ? (
                  <div className="text-center py-16 bg-slate-950/10 border border-dashed border-slate-850 rounded-2xl p-6 text-slate-500 text-xs italic leading-relaxed">
                    No compiled itinerary plans yet. Message your coordinator agent to compile one!
                  </div>
                ) : (
                  itineraries.map((it) => (
                    <div key={it.id} className="bg-slate-950/40 border border-slate-850/80 rounded-2xl p-5 space-y-3 text-xs animate-fade-in">
                      <div className="flex justify-between items-center text-slate-100 font-semibold border-b border-slate-850/50 pb-2">
                        <span className="text-indigo-400">Day {it.day_number}</span>
                        <span className="text-[10px] text-slate-500">{it.title}</span>
                      </div>
                      <p className="text-slate-400 leading-relaxed font-sans whitespace-pre-line text-[11px]">
                        {it.description}
                      </p>
                      
                      {it.activities && typeof it.activities === "object" && (
                        <div className="flex flex-wrap gap-1.5 pt-2">
                          {Object.values(it.activities).flat().map((act: any, idx: number) => (
                            <span key={idx} className="bg-slate-950 text-indigo-400 border border-slate-850 px-2 py-0.5 rounded text-[9px] font-mono">
                              {String(act)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </aside>

          </div>
        )}
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
