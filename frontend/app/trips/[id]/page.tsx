"use client";

import { useEffect, useState, useRef, FormEvent, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { getSessionToken, signOut } from "@/lib/supabase";
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { LogOut, Send, Terminal, Calendar, Loader, Compass, ChevronLeft, CheckCircle, Plane, Home, Cpu, Activity, Sparkles } from "lucide-react";

// Helper function to parse basic Markdown (headers, lists, bold, inline code)
function renderMarkdown(content: string) {
  if (!content) return null;
  const lines = content.split("\n");
  
  return (
    <div className="space-y-2 font-sans">
      {lines.map((line, idx) => {
        // Headers
        if (line.startsWith("### ")) {
          return (
            <h3 key={idx} className="text-xs font-bold uppercase tracking-wider text-indigo-400 mt-4 mb-2 flex items-center gap-1.5">
              {line.substring(4)}
            </h3>
          );
        }
        if (line.startsWith("## ")) {
          return (
            <h2 key={idx} className="text-sm font-bold text-white mt-5 mb-2 border-b border-slate-800/80 pb-1">
              {line.substring(3)}
            </h2>
          );
        }
        if (line.startsWith("# ")) {
          return (
            <h1 key={idx} className="text-base font-extrabold text-white mt-6 mb-3">
              {line.substring(2)}
            </h1>
          );
        }
        
        // Unordered lists
        if (line.startsWith("- ") || line.startsWith("* ")) {
          const listText = line.substring(2);
          return (
            <div key={idx} className="flex items-start gap-2 ml-2 my-1">
              <span className="text-indigo-400 mt-1 select-none font-sans text-xs">•</span>
              <p className="text-xs text-slate-300 leading-relaxed flex-1">
                {parseInlineStyle(listText)}
              </p>
            </div>
          );
        }
        
        // Blank lines
        if (line.trim() === "") {
          return <div key={idx} className="h-1.5" />;
        }
        
        // Regular paragraphs
        return (
          <p key={idx} className="text-xs text-slate-305 leading-relaxed">
            {parseInlineStyle(line)}
          </p>
        );
      })}
    </div>
  );
}

// Helper to parse **bold** and `code` styles inline
function parseInlineStyle(text: string) {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="text-white font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="bg-slate-950 px-1.5 py-0.5 rounded font-mono text-[10px] text-indigo-300 border border-slate-800">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

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
  const [activeAgent, setActiveAgent] = useState<string | null>(null);


  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  const fetchItineraries = useCallback(async () => {
    try {
      setItinerariesLoading(true);
      const data = await apiFetch<Itinerary[]>(`/trips/${tripId}/itineraries`);
      setItineraries(data);
    } catch (err) {
      console.error("Failed to load itineraries:", err);
    } finally {
      setItinerariesLoading(false);
    }
  }, [tripId]);

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
  }, [tripId, fetchItineraries]);

  // Scroll to bottom on new messages
  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    const userText = inputMessage.trim();
    setInputMessage("");
    setIsSending(true);
    setSendError(null);
    setActiveLogs([]);
    setActiveAgent("CoordinatorAgent");

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

      // Removed auto-focus to console tab to keep user in chat view

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
                setActiveAgent(data.agent);
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
                setActiveAgent(null);
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

  const getStepStatus = (stepAgent: string) => {
    if (!isSending) {
      return activeLogs.length > 0 ? "completed" : "idle";
    }
    const agentOrder = ["CoordinatorAgent", "LogisticsAgent", "AccommodationAgent", "ExperienceAgent", "SupervisorAgent"];
    const currentIndex = agentOrder.indexOf(activeAgent || "");
    const stepIndex = agentOrder.indexOf(stepAgent);
    if (stepIndex < currentIndex) return "completed";
    if (stepIndex === currentIndex) return "active";
    return "idle";
  };

  const steps = [
    { name: "Coordinator", key: "CoordinatorAgent", icon: Terminal },
    { name: "Logistics", key: "LogisticsAgent", icon: Plane },
    { name: "Lodging", key: "AccommodationAgent", icon: Home },
    { name: "Experiences", key: "ExperienceAgent", icon: Activity },
    { name: "Supervisor", key: "SupervisorAgent", icon: Cpu }
  ];

  return (
    <main className="h-screen overflow-hidden bg-[#0b0f19] text-slate-100 font-sans flex flex-col">
      <Navbar />

      <div className="max-w-7xl w-full mx-auto px-6 py-6 flex-1 flex flex-col space-y-4 overflow-hidden">
        
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
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
            
            {/* Left & Middle Column: Interactive Workspace */}
            <div className="lg:col-span-2 flex flex-col min-h-0 border border-slate-700/60 bg-[#0c101a]/70 rounded-[2rem] overflow-hidden backdrop-blur-xl shadow-2xl shadow-indigo-900/20 relative group">
              <div className="absolute inset-0 bg-gradient-to-b from-indigo-500/5 to-transparent pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
              
              {/* Pipeline Stepper (Always Visible at Top) */}
              <div className="bg-slate-950/40 border-b border-slate-700/50 p-4 shrink-0 select-none">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 font-sans">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    Live Agent Orchestration Pipeline
                  </h4>
                  {isSending && (
                    <span className="flex items-center gap-1.5 text-[10px] text-indigo-400 font-semibold animate-pulse">
                      <Loader className="w-3 h-3 animate-spin" /> Agents Processing...
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-5 gap-2 relative">
                  {steps.map((step, idx) => {
                    const status = getStepStatus(step.key);
                    const Icon = step.icon;
                    
                    return (
                      <div key={step.key} className="flex flex-col items-center text-center relative group">
                        {idx < steps.length - 1 && (
                          <div className={`absolute top-3 left-[60%] right-[-40%] h-[1.5px] z-0 transition-colors duration-500 ${
                            status === "completed" ? "bg-emerald-500/50" : "bg-slate-800"
                          }`} />
                        )}
                        
                        <div className={`w-6 h-6 rounded-lg flex items-center justify-center z-10 transition-all duration-500 border ${
                          status === "completed"
                            ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-400 shadow-md shadow-emerald-950/20"
                            : status === "active"
                            ? "bg-indigo-500/10 border-indigo-500 text-indigo-400 animate-pulse shadow-lg shadow-indigo-500/20 scale-105"
                            : "bg-slate-900/60 border-slate-850 text-slate-500"
                        }`}>
                          <Icon className="w-3 h-3" />
                        </div>
                        
                        <span className={`text-[8px] font-bold mt-1.5 transition-colors duration-300 font-sans ${
                          status === "completed" ? "text-emerald-400" : status === "active" ? "text-indigo-400" : "text-slate-500"
                        }`}>
                          {step.name}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Workspace Content Panels */}
              <div className="flex-1 overflow-y-auto p-6 min-h-0">
                  {/* Chat Bubbles View */}
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
                            className={`max-w-[85%] rounded-2xl px-6 py-4 text-[13px] leading-relaxed relative ${
                              message.sender === "user"
                                ? "bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-700 text-white shadow-xl shadow-indigo-500/25 border border-indigo-400/20"
                                : "bg-slate-800/60 backdrop-blur-md border border-slate-700/50 text-slate-100 shadow-lg shadow-black/20"
                            }`}
                          >
                            {message.sender === "assistant" && (
                               <div className="absolute -left-2 top-4 w-1.5 h-6 bg-indigo-500 rounded-r-full shadow-[0_0_8px_rgba(99,102,241,0.8)]" />
                            )}
                            {message.sender === "user" ? (
                              message.content
                            ) : (
                              renderMarkdown(message.content)
                            )}
                          </div>
                        </div>
                      ))
                    )}
                    <div ref={scrollAnchorRef} />
                  </div>
              </div>

              {/* Form Input Area */}
              <form
                onSubmit={handleSend}
                className="border-t border-slate-700/50 p-5 bg-slate-900/80 backdrop-blur-xl flex items-end gap-3 shrink-0 relative z-10"
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
                  className="flex-1 resize-none bg-slate-950/50 border border-slate-700/60 rounded-[1.25rem] px-5 py-3.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/70 focus:border-indigo-500/70 transition-all duration-300 max-h-32 font-sans shadow-inner shadow-black/40"
                />
                <button
                  type="submit"
                  disabled={!inputMessage.trim() || isSending}
                  className="w-12 h-12 shrink-0 flex items-center justify-center bg-gradient-to-br from-indigo-500 via-purple-600 to-indigo-600 hover:from-indigo-400 hover:to-purple-500 disabled:from-slate-800 disabled:to-slate-800 disabled:cursor-not-allowed rounded-[1.25rem] shadow-lg hover:shadow-indigo-500/40 hover:scale-105 active:scale-95 transition-all duration-300 group"
                >
                  <Send className="w-5 h-5 text-white group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                </button>
              </form>
              {sendError && (
                <div className="px-6 pb-4 text-xs text-red-400 bg-slate-950/15">{sendError}</div>
              )}
            </div>

            {/* Right Column: Compiled Itineraries Display */}
            <aside className="border min-h-0 border-slate-700/60 bg-[#0c101a]/70 rounded-[2rem] p-6 flex flex-col space-y-5 backdrop-blur-xl shadow-2xl shadow-purple-900/10">
              <div className="flex items-center gap-3 text-xs font-bold text-slate-300 uppercase tracking-widest border-b border-slate-700/50 pb-4 select-none shrink-0">
                <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                  <Calendar className="w-4 h-4 text-indigo-400" />
                </div>
                <span className="bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">Generated Itineraries</span>
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
                    <div key={it.id} className="bg-slate-800/40 border border-slate-700/50 hover:border-indigo-500/30 rounded-2xl p-5 space-y-3 text-xs transition-all duration-300 hover:shadow-lg hover:shadow-indigo-500/10 group cursor-default">
                      <div className="flex justify-between items-center text-slate-100 font-semibold border-b border-slate-700/50 pb-3">
                        <span className="bg-indigo-500/10 text-indigo-400 px-2 py-1 rounded-md border border-indigo-500/20">Day {it.day_number}</span>
                        <span className="text-[11px] text-slate-300 font-medium group-hover:text-indigo-300 transition-colors">{it.title}</span>
                      </div>
                      <div className="text-slate-300 leading-relaxed font-sans text-[12px] group-hover:text-slate-200 transition-colors">
                        {renderMarkdown(it.description)}
                      </div>
                      
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
