"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/refine/dataProvider";

/**
 * Who is signed in, which branch is active, and what they may do there.
 * Permission patterns come from /api/auth/me and are evaluated exactly like
 * apps/org/rbac.py (fnmatch `*`, `-` denies). The UI uses this only to hide
 * menus and buttons — the backend checks every request regardless.
 */
export interface MeBranch {
  id: number;
  code: string;
  name: string;
  name_hi: string;
  roles: string[];
  permissions: Record<string, string[]>;
}

export interface Me {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  preferred_language: "en" | "hi";
  group_admin: boolean;
  branches: MeBranch[];
}

export type Lang = "en" | "hi";

interface Session {
  me: Me | null;
  branch: MeBranch | null; // null with allBranches=true or before load
  allBranches: boolean;
  lang: Lang;
  can: (perm: string) => boolean;
  setBranch: (id: number | "all") => void;
  setLang: (lang: Lang) => void;
}

const SessionContext = createContext<Session | null>(null);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

function writeCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
}

const patternCache = new Map<string, RegExp>();
function matches(pattern: string, perm: string): boolean {
  let re = patternCache.get(pattern);
  if (!re) {
    re = new RegExp(`^${pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`);
    patternCache.set(pattern, re);
  }
  return re.test(perm);
}

export function roleAllows(patterns: string[], perm: string): boolean {
  if (patterns.some((p) => p.startsWith("-") && matches(p.slice(1), perm))) return false;
  return patterns.some((p) => !p.startsWith("-") && matches(p, perm));
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [branchChoice, setBranchChoice] = useState<string | null>(null);
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setBranchChoice(readCookie("eraj_branch"));
    const l = readCookie("eraj_lang");
    if (l === "hi" || l === "en") setLangState(l);
    api.get<Me>("auth/me/").then((data) => {
      setMe(data);
      const current = readCookie("eraj_branch");
      const valid =
        (current === "all" && data.group_admin) || data.branches.some((b) => String(b.id) === current);
      if (!valid && data.branches.length) {
        // Prefer the branch where the user holds a working role (e.g. the owner
        // is Admin of Patna and only group admin elsewhere), not just A–Z first.
        const home = data.branches.find((b) => b.roles.some((r) => r !== "group_admin")) ?? data.branches[0];
        writeCookie("eraj_branch", String(home.id));
        setBranchChoice(String(home.id));
      }
      if (!readCookie("eraj_lang")) {
        writeCookie("eraj_lang", data.preferred_language);
        setLangState(data.preferred_language);
      }
    });
  }, []);

  const value = useMemo<Session>(() => {
    const allBranches = branchChoice === "all";
    const branch = me?.branches.find((b) => String(b.id) === branchChoice) ?? null;
    // All-branches view: only group-admin patterns apply (read-only, server-enforced).
    const patternSets = allBranches
      ? me?.group_admin
        ? [["*"]]
        : []
      : Object.values(branch?.permissions ?? {});
    return {
      me,
      branch,
      allBranches,
      lang,
      can: (perm) => patternSets.some((p) => roleAllows(p, perm)),
      setBranch: (id) => {
        writeCookie("eraj_branch", String(id));
        window.location.reload(); // every cached list belongs to the old branch
      },
      setLang: (l) => {
        writeCookie("eraj_lang", l);
        setLangState(l);
      },
    };
  }, [me, branchChoice, lang]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
