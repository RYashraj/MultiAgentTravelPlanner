"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

export function Navbar() {
  const { user, isLoading, signOut } = useAuth();
  const router = useRouter();

  const handleSignOut = async () => {
    await signOut();
    router.push("/");
  };

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/40 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
        <Link href="/" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <svg
              className="w-5 h-5 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
              VoyagerAI
            </h1>
            <p className="text-[10px] text-indigo-400 font-mono tracking-wider uppercase">
              Multi-Agent Planner
            </p>
          </div>
        </Link>

        <nav className="flex items-center gap-3">
          {isLoading ? (
            <div className="w-24 h-8 rounded-lg bg-slate-800/60 animate-pulse" />
          ) : user ? (
            <>
              <Link
                href="/trips"
                className="hidden sm:inline text-sm text-slate-300 hover:text-white transition-colors px-3 py-2"
              >
                My Trips
              </Link>
              <span className="hidden md:inline text-xs text-slate-500 font-mono px-3 py-1 rounded-full border border-slate-800 bg-slate-900/60">
                {user.email}
              </span>
              <button
                onClick={handleSignOut}
                className="text-sm font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700/60 rounded-lg px-4 py-2 transition-all"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm font-medium text-slate-300 hover:text-white transition-colors px-4 py-2"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="text-sm font-medium text-white bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 rounded-lg px-4 py-2 shadow-lg shadow-indigo-500/25 transition-all"
              >
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
