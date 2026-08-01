'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, Sparkles, Calendar } from 'lucide-react';

interface ItineraryCardProps {
  content: string;
  destination: string;
  createdAt?: string;
}

function parseInlineStyle(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="bg-white/10 px-1 rounded text-xs font-mono text-indigo-200">{part.slice(2, -2)}</code>;
    }
    return part;
  });
}

export function ItineraryCard({ content, destination, createdAt }: ItineraryCardProps) {
  const [expanded, setExpanded] = useState(true);

  const lines = content.split('\n');

  const renderLine = (line: string, idx: number) => {
    if (line.startsWith('# ')) {
      return (
        <h1 key={idx} className="text-xl font-extrabold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent mt-4 mb-2">
          {parseInlineStyle(line.substring(2))}
        </h1>
      );
    }
    if (line.startsWith('## ')) {
      return (
        <h2 key={idx} className="text-base font-bold text-white mt-6 mb-2 border-b border-white/10 pb-1">
          {parseInlineStyle(line.substring(3))}
        </h2>
      );
    }
    if (line.startsWith('### ')) {
      return (
        <h3 key={idx} className="text-sm font-bold text-indigo-300 mt-4 mb-1 flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-indigo-400 shrink-0" />
          {line.substring(4)}
        </h3>
      );
    }
    if (line.startsWith('---')) {
      return <hr key={idx} className="border-white/10 my-3" />;
    }
    if (line.startsWith('- ') || line.startsWith('* ')) {
      return (
        <div key={idx} className="flex items-start gap-2 ml-2 my-1">
          <div className="mt-2 w-1 h-1 rounded-full bg-indigo-400/60 shrink-0" />
          <p className="text-xs text-slate-300 leading-relaxed">{parseInlineStyle(line.substring(2))}</p>
        </div>
      );
    }
    if (line.trim() === '') return <div key={idx} className="h-1" />;
    return (
      <p key={idx} className="text-xs text-slate-300 leading-relaxed">{parseInlineStyle(line)}</p>
    );
  };

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Calendar className="w-4 h-4 text-white" />
          </div>
          <div className="text-left">
            <p className="text-sm font-semibold text-white">Full Itinerary — {destination}</p>
            {createdAt && (
              <p className="text-[10px] text-slate-500">
                Generated {new Date(createdAt).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>

      {expanded && (
        <div className="px-5 pb-5 max-h-[600px] overflow-y-auto space-y-0.5">
          {lines.map((line, idx) => renderLine(line, idx))}
        </div>
      )}
    </div>
  );
}
