"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { isMockMode } from "@/lib/supabase";
import { Mail, Lock, ShieldCheck, AlertCircle, Compass } from "lucide-react";
import { Navbar } from "@/components/Navbar";

export default function SignupPage() {
  const router = useRouter();
  const { signUpWithPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setErrorMsg("Please enter an email address");
      return;
    }
    if (!isMockMode) {
      if (!password) {
        setErrorMsg("Please enter a password");
        return;
      }
      if (password !== confirmPassword) {
        setErrorMsg("Passwords do not match");
        return;
      }
    }

    setLoading(true);
    setErrorMsg(null);

    try {
      const { error } = await signUpWithPassword(email, password);
      if (error) {
        setErrorMsg(error || "Failed to create account");
      } else {
        router.push("/trips");
      }
    } catch (err) {
      setErrorMsg("An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans flex flex-col relative overflow-hidden">
      {/* Background Gradients */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[100px] pointer-events-none" />

      <Navbar />

      <div className="flex-1 flex items-center justify-center px-6 relative z-10 py-12">
        <div className="w-full max-w-md space-y-8">
          {/* Title/Logo */}
          <div className="text-center space-y-3">
            <div className="inline-flex items-center gap-3 bg-slate-900/60 border border-slate-800/80 px-4 py-2 rounded-2xl backdrop-blur-sm">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/35">
                <Compass className="w-4.5 h-4.5 text-white" />
              </div>
              <div>
                <h1 className="text-md font-bold tracking-tight bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                  VoyagerAI
                </h1>
              </div>
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-white mt-4">Create your account</h2>
            <p className="text-sm text-slate-400">Join to plan your trip with AI agents</p>
          </div>

          {/* Signup Card */}
          <div className="bg-slate-900/50 border border-slate-800/80 rounded-3xl p-8 backdrop-blur-md shadow-2xl shadow-indigo-950/10 space-y-6">
            
            {/* Mock Auth Mode Notice */}
            {isMockMode && (
              <div className="bg-indigo-950/30 border border-indigo-500/20 rounded-2xl p-4 flex items-start gap-3">
                <ShieldCheck className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-semibold text-indigo-300">Mock Registration Mode</h4>
                  <p className="text-[10px] text-slate-400 mt-1 leading-relaxed">
                    Provide any email to simulate instant account creation and session authentication.
                  </p>
                </div>
              </div>
            )}

            {/* Error Banner */}
            {errorMsg && (
              <div className="bg-red-950/30 border border-red-500/30 text-red-200 rounded-2xl p-4 flex items-center gap-3 text-xs">
                <AlertCircle className="w-4.5 h-4.5 text-red-400 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleSignup} className="space-y-5">
              {/* Email Field */}
              <div className="space-y-2">
                <label htmlFor="email" className="text-xs font-medium text-slate-300 tracking-wider">
                  Email Address
                </label>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500 group-focus-within:text-indigo-400 transition-colors">
                    <Mail className="w-4.5 h-4.5" />
                  </div>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    className="w-full bg-slate-950/80 border border-slate-800/80 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans"
                    required
                  />
                </div>
              </div>

              {/* Password Field */}
              <div className="space-y-2">
                <label htmlFor="password" className="text-xs font-medium text-slate-300 tracking-wider">
                  Password
                </label>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500 group-focus-within:text-indigo-400 transition-colors">
                    <Lock className="w-4.5 h-4.5" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={isMockMode ? "Optional in Mock Mode" : "Minimum 6 characters"}
                    className="w-full bg-slate-950/80 border border-slate-800/80 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans"
                    required={!isMockMode}
                  />
                </div>
              </div>

              {/* Confirm Password Field */}
              {!isMockMode && (
                <div className="space-y-2">
                  <label htmlFor="confirmPassword" className="text-xs font-medium text-slate-300 tracking-wider">
                    Confirm Password
                  </label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500 group-focus-within:text-indigo-400 transition-colors">
                      <Lock className="w-4.5 h-4.5" />
                    </div>
                    <input
                      id="confirmPassword"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full bg-slate-950/80 border border-slate-800/80 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans"
                      required
                    />
                  </div>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-indigo-900/50 disabled:to-purple-900/50 disabled:cursor-not-allowed font-medium text-sm text-white rounded-xl shadow-lg shadow-indigo-500/20 transition-all flex items-center justify-center gap-2 mt-2"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Creating account...
                  </>
                ) : (
                  "Create Account"
                )}
              </button>
            </form>

            {/* Toggle Login Link */}
            <div className="text-center text-xs text-slate-500 pt-2">
              Already have an account?{" "}
              <Link href="/login" className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors">
                Sign in instead
              </Link>
            </div>

          </div>
        </div>
      </div>
    </main>
  );
}
