"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase, isMockMode } from "@/lib/supabase";

/**
 * Auth Callback Handler
 * 
 * Supabase email confirmation links redirect here with a ?code= param.
 * This page exchanges the code for a session, stores the token,
 * then redirects the user to /trips — all in the SAME tab.
 * 
 * This prevents the "new tab opens" issue when confirming email.
 */
export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    if (isMockMode || !supabase) {
      // Mock mode: nothing to exchange, just go to trips
      router.replace("/trips");
      return;
    }

    const handleCallback = async () => {
      try {
        // exchangeCodeForSession handles the ?code= param from the URL
        const { data, error } = await supabase!.auth.exchangeCodeForSession(
          window.location.href
        );

        if (error) {
          console.error("Auth callback error:", error);
          router.replace("/login?error=confirmation_failed");
          return;
        }

        if (data?.session) {
          localStorage.setItem("voyager_auth_token", data.session.access_token);
          localStorage.setItem("voyager_user_email", data.session.user?.email || "");
        }

        // Redirect to trips page — same tab, no new window
        router.replace("/trips");
      } catch (err) {
        console.error("Unexpected auth callback error:", err);
        router.replace("/login?error=unexpected");
      }
    };

    handleCallback();
  }, [router]);

  return (
    <main className="h-screen bg-[var(--color-bg)] flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center mx-auto shadow-lg shadow-indigo-500/30 animate-pulse">
          <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-[var(--color-text-secondary)] text-sm font-medium">Confirming your account…</p>
        <p className="text-[var(--color-text-muted)] text-xs">You&apos;ll be redirected in a moment.</p>
      </div>
    </main>
  );
}
