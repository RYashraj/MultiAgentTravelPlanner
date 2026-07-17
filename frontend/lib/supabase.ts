import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

// Only initialize Supabase if URL and Key are actually populated
export const isMockMode = !supabaseUrl || !supabaseAnonKey;

export const supabase = isMockMode
  ? null
  : createClient(supabaseUrl, supabaseAnonKey);

export interface AuthUser {
  email: string;
  token: string;
}

/**
 * Get active auth session token (real JWT or local mock token)
 */
export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("voyager_auth_token");
}

/**
 * Get active user email
 */
export function getUserEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("voyager_user_email");
}

/**
 * Sign in using email/password (or Mock Auth if keys are empty)
 */
export async function signIn(email: string, password?: string): Promise<{ data: any; error: any }> {
  if (isMockMode) {
    // Mock Auth logic
    const mockToken = `mock-user-${email}`;
    localStorage.setItem("voyager_auth_token", mockToken);
    localStorage.setItem("voyager_user_email", email);
    return { data: { user: { email }, session: { access_token: mockToken } }, error: null };
  }

  // Real Supabase Auth logic
  if (!supabase) return { data: null, error: new Error("Supabase client not initialized") };
  
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password: password || "",
  });

  if (data?.session) {
    localStorage.setItem("voyager_auth_token", data.session.access_token);
    localStorage.setItem("voyager_user_email", data.user?.email || email);
  }

  return { data, error };
}

/**
 * Sign up a new user (or Mock Auth if keys are empty)
 */
export async function signUp(email: string, password?: string): Promise<{ data: any; error: any }> {
  if (isMockMode) {
    // Mock Signup mimics instant login
    const mockToken = `mock-user-${email}`;
    localStorage.setItem("voyager_auth_token", mockToken);
    localStorage.setItem("voyager_user_email", email);
    return { data: { user: { email }, session: { access_token: mockToken } }, error: null };
  }

  // Real Supabase Signup logic
  if (!supabase) return { data: null, error: new Error("Supabase client not initialized") };

  const { data, error } = await supabase.auth.signUp({
    email,
    password: password || "",
  });

  if (data?.session) {
    localStorage.setItem("voyager_auth_token", data.session.access_token);
    localStorage.setItem("voyager_user_email", data.user?.email || email);
  }

  return { data, error };
}

/**
 * Sign out of current session (Mock or Real)
 */
export async function signOut(): Promise<{ error: any }> {
  localStorage.removeItem("voyager_auth_token");
  localStorage.removeItem("voyager_user_email");

  if (!isMockMode && supabase) {
    const { error } = await supabase.auth.signOut();
    return { error };
  }

  return { error: null };
}
