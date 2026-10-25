import { cookies } from "next/headers";

/**
 * Session cookies (ADR-004): JWTs live only in httpOnly cookies set by the
 * Next server. Browser code never sees a token; it calls /api/proxy/* and the
 * proxy attaches `Authorization: Bearer` server-side.
 */
export const ACCESS = "eraj_access";
export const REFRESH = "eraj_refresh";
export const BRANCH = "eraj_branch"; // chosen branch id or "all" — a choice, re-checked by the backend
export const LANG = "eraj_lang"; // "en" | "hi"

const secure = process.env.NODE_ENV === "production";

export const ACCESS_OPTS = {
  httpOnly: true,
  secure,
  sameSite: "lax" as const,
  path: "/",
  maxAge: 60 * 15, // SIMPLE_JWT ACCESS_TOKEN_LIFETIME
};

export const REFRESH_OPTS = {
  httpOnly: true,
  secure,
  sameSite: "lax" as const,
  path: "/",
  maxAge: 60 * 60 * 24, // SIMPLE_JWT REFRESH_TOKEN_LIFETIME
};

/** Readable anywhere (Server Components included). */
export async function getAccessToken(): Promise<string | null> {
  return (await cookies()).get(ACCESS)?.value ?? null;
}

export async function getRefreshToken(): Promise<string | null> {
  return (await cookies()).get(REFRESH)?.value ?? null;
}

/** Server Actions / Route Handlers only (Server Components cannot set cookies). */
export async function setAccessToken(token: string): Promise<void> {
  (await cookies()).set(ACCESS, token, ACCESS_OPTS);
}

export async function setSession(access: string, refresh: string): Promise<void> {
  const jar = await cookies();
  jar.set(ACCESS, access, ACCESS_OPTS);
  jar.set(REFRESH, refresh, REFRESH_OPTS);
}

export async function clearSession(): Promise<void> {
  const jar = await cookies();
  for (const name of [ACCESS, REFRESH, BRANCH]) jar.delete(name);
}
