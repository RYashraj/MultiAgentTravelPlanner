"use client";

import { useState } from "react";
import { getSessionToken } from "../lib/supabase";
import { X, MapPin, Compass } from "lucide-react";

interface TripCreationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTripCreated: (trip: any) => void;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function TripCreationModal({
  isOpen,
  onClose,
  onTripCreated,
}: TripCreationModalProps) {
  const [destination, setDestination] = useState("");
  const [status, setStatus] = useState("draft");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!destination.trim()) {
      setErrorMsg("Please enter a destination");
      return;
    }

    setLoading(true);
    setErrorMsg(null);

    const token = getSessionToken();
    if (!token) {
      setErrorMsg("Authentication session expired. Please sign in again.");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/trips`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          destination: destination.trim(),
          status,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to create trip");
      }

      const newTrip = await res.json();
      onTripCreated(newTrip);
      setDestination("");
      setStatus("draft");
      onClose();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to plan trip. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop Backdrop blur */}
      <div
        className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="bg-slate-900 border border-slate-800/80 rounded-3xl w-full max-w-md overflow-hidden relative z-10 shadow-2xl animate-fade-in">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-teal-500" />
        
        {/* Header */}
        <div className="p-6 border-b border-slate-800/60 flex justify-between items-center">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-indigo-500/10 flex items-center justify-center">
              <Compass className="w-4 h-4 text-indigo-400" />
            </div>
            <h3 className="font-semibold text-white text-base">Plan a new trip</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors border border-slate-700/30"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          
          {errorMsg && (
            <div className="bg-red-950/20 border border-red-500/20 text-red-200 rounded-2xl p-4 text-xs">
              {errorMsg}
            </div>
          )}

          {/* Destination */}
          <div className="space-y-2">
            <label htmlFor="destination" className="text-xs font-medium text-slate-300 tracking-wider">
              Where to?
            </label>
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500 group-focus-within:text-indigo-400 transition-colors">
                <MapPin className="w-4 h-4" />
              </div>
              <input
                id="destination"
                type="text"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="e.g. Tokyo, Paris, New York"
                className="w-full bg-slate-950/80 border border-slate-800/80 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans"
                required
                autoFocus
              />
            </div>
          </div>

          {/* Status Selection */}
          <div className="space-y-2">
            <label htmlFor="status" className="text-xs font-medium text-slate-300 tracking-wider">
              Planning Status
            </label>
            <select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full bg-slate-950/80 border border-slate-800/80 rounded-xl py-3 px-4 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans appearance-none cursor-pointer"
            >
              <option value="draft">Draft (Private Notes)</option>
              <option value="planning">Planning (Actively researching)</option>
              <option value="ready">Ready (Itinerary generated)</option>
              <option value="booked">Booked (Reservations confirmed)</option>
            </select>
          </div>

          {/* Submit */}
          <div className="pt-2 flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 border border-slate-800 hover:bg-slate-800 font-medium text-sm text-slate-300 rounded-xl transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-indigo-900/50 disabled:to-purple-900/50 disabled:cursor-not-allowed font-medium text-sm text-white rounded-xl shadow-lg shadow-indigo-500/25 transition-all flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Planning...
                </>
              ) : (
                "Plan Trip"
              )}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
}
