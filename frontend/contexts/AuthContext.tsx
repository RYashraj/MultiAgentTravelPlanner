"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { 
  supabase, 
  isMockMode, 
  getSessionToken, 
  getUserEmail, 
  signIn, 
  signUp, 
  signOut as supabaseSignOut 
} from "@/lib/supabase";

type AuthContextValue = {
  user: any | null;
  session: any | null;
  isLoading: boolean;
  signInWithPassword: (
    email: string,
    password?: string
  ) => Promise<{ error: string | null }>;
  signUpWithPassword: (
    email: string,
    password?: string
  ) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<any | null>(null);
  const [user, setUser] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    if (isMockMode) {
      const token = getSessionToken();
      const email = getUserEmail();
      if (token && email) {
        const mockSession = { access_token: token };
        const mockUser = { email, id: token.replace("mock-user-", "") };
        setSession(mockSession);
        setUser(mockUser);
      } else {
        setSession(null);
        setUser(null);
      }
      setIsLoading(false);
    } else if (supabase) {
      supabase.auth.getSession().then(({ data }) => {
        if (!mounted) return;
        setSession(data.session);
        setUser(data.session?.user ?? null);
        if (data.session) {
          localStorage.setItem("voyager_auth_token", data.session.access_token);
          localStorage.setItem("voyager_user_email", data.session.user?.email || "");
        } else {
          localStorage.removeItem("voyager_auth_token");
          localStorage.removeItem("voyager_user_email");
        }
        setIsLoading(false);
      });

      const { data: listener } = supabase.auth.onAuthStateChange(
        (_event, newSession) => {
          if (!mounted) return;
          setSession(newSession);
          setUser(newSession?.user ?? null);
          if (newSession) {
            localStorage.setItem("voyager_auth_token", newSession.access_token);
            localStorage.setItem("voyager_user_email", newSession.user?.email || "");
          } else {
            localStorage.removeItem("voyager_auth_token");
            localStorage.removeItem("voyager_user_email");
          }
          setIsLoading(false);
        }
      );

      return () => {
        mounted = false;
        listener.subscription.unsubscribe();
      };
    } else {
      setIsLoading(false);
    }
  }, []);

  const signInWithPassword: AuthContextValue["signInWithPassword"] = async (
    email,
    password
  ) => {
    setIsLoading(true);
    const { data, error } = await signIn(email, password);
    if (!error && data?.session) {
      setSession(data.session);
      setUser(data.user || { email, id: data.session.access_token.replace("mock-user-", "") });
    }
    setIsLoading(false);
    return { error: error?.message ?? null };
  };

  const signUpWithPassword: AuthContextValue["signUpWithPassword"] = async (
    email,
    password
  ) => {
    setIsLoading(true);
    const { data, error } = await signUp(email, password);
    if (!error && data?.session) {
      setSession(data.session);
      setUser(data.user || { email, id: data.session.access_token.replace("mock-user-", "") });
    }
    setIsLoading(false);
    return { error: error?.message ?? null };
  };

  const signOut = async () => {
    setIsLoading(true);
    await supabaseSignOut();
    setSession(null);
    setUser(null);
    setIsLoading(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        isLoading,
        signInWithPassword,
        signUpWithPassword,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
