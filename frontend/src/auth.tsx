import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { storage } from "@/src/utils/storage";
import { api, TOKEN_KEY } from "@/src/api";
import { clearMood } from "@/src/avatar";

export type User = {
  id: string;
  email: string;
  name: string;
  onboarded: boolean;
  age?: number | null;
  focus_areas?: string[] | null;
  /** One of the eight focus areas (backend/focus_areas.py), with its goal and plan. */
  focus_area?: string | null;
  focus_goal?: { goal?: string | null; plan?: string | null } | null;
  /** Usual bedtime and wake time ("HH:MM", study time zone); null until set. */
  sleep_schedule?: { bedtime: string; wake: string } | null;
  avatar?: import("./avatar").AvatarConfig | null;
  /** True when a TAMU AI key is usable (Future Me's conversation needs it). */
  tamus_ai_available?: boolean;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    if (token) {
      try {
        const me = await api.me();
        setUser(me);
      } catch {
        await storage.secureRemove(TOKEN_KEY);
        setUser(null);
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const signIn = async (email: string, password: string) => {
    const res = await api.login(email, password);
    await storage.secureSet(TOKEN_KEY, res.token);
    setUser(res.user);
  };

  const signUp = async (email: string, password: string, name: string, code: string) => {
    const res = await api.signup(email, password, name, code);
    await storage.secureSet(TOKEN_KEY, res.token);
    setUser(res.user);
  };

  const signOut = async () => {
    // Audit finding #2: previously only cleared the local token, leaving
    // the server-side session valid for its full life if it leaked.
    try {
      await api.logout();
    } catch {
      // Best-effort — if the network call fails, still clear locally so
      // the user isn't stuck unable to sign out.
    }
    await storage.secureRemove(TOKEN_KEY);
    clearMood();
    setUser(null);
  };

  const refresh = async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      /* ignore */
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signUp, signOut, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
