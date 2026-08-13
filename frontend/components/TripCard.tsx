"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export type Trip = {
  id: string;
  destination: string;
  created_at: string;
  is_saved?: boolean;
};

type TripCardProps = {
  trip: Trip;
  onOpen: (tripId: string) => void;
  onDeleted: (tripId: string) => void;
  onSavedChange?: (tripId: string, isSaved: boolean) => void;
};

export function TripCard({ trip, onOpen, onDeleted, onSavedChange }: TripCardProps) {
  const [isSaved, setIsSaved] = useState(!!trip.is_saved);
  const [isSaving, setIsSaving] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this trip?")) return;
    try {
      await apiFetch(`/trips/${trip.id}`, { method: "DELETE" });
      onDeleted(trip.id);
    } catch {
      alert("Failed to delete trip.");
    }
  };

  const handleToggleSave = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isSaving) return;
    const next = !isSaved;
    setIsSaved(next); // optimistic
    setIsSaving(true);
    try {
      await apiFetch(`/trips/${trip.id}/save`, {
        method: "POST",
        body: JSON.stringify({ saved: next }),
      });
      onSavedChange?.(trip.id, next);
    } catch (err) {
      setIsSaved(!next); // revert
      if (!(err instanceof ApiError && err.status === 404)) {
        alert("Couldn't update saved status. Try again in a bit.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <button
      onClick={() => onOpen(trip.id)}
      className="text-left bg-[var(--color-surface-alt)] backdrop-blur-md border border-[var(--color-border)] rounded-2xl p-5 hover:border-indigo-400 hover:bg-[var(--color-surface-hover)] hover:-translate-y-1 hover:shadow-xl hover:shadow-indigo-500/10 transition-all duration-300 group relative"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 transition-all">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </span>
        <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
          {new Date(trip.created_at).toLocaleDateString()}
        </span>
      </div>
      <h3 className="font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-text-primary)] text-lg pr-2">
        {trip.destination}
      </h3>
      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
          Open itinerary
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </p>

        <div className="flex items-center gap-1">
          {/* Save/bookmark toggle */}
          <div
            onClick={handleToggleSave}
            title={isSaved ? "Remove from saved" : "Save trip"}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
              isSaved
                ? "text-amber-400 opacity-100 hover:bg-amber-500/20"
                : "text-[var(--color-text-muted)] opacity-0 group-hover:opacity-100 hover:bg-amber-500/20 hover:text-amber-400"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill={isSaved ? "currentColor" : "none"}
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
          </div>

          {/* Delete */}
          <div
            onClick={handleDelete}
            title="Delete trip"
            className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--color-text-muted)] hover:bg-red-500/20 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </div>
        </div>
      </div>
    </button>
  );
}
