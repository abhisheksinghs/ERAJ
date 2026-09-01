import { cookies } from "next/headers";

const ACCESS = "eraj_access";

const COOKIE_OPTS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  // Matches SIMPLE_JWT ACCESS_TOKEN_LIFETIME (15 min). ponytail: no refresh
  // flow — the user re-signs in when it expires. Add /auth/refresh when
  // sessions need to outlast the access token.
  maxAge: 60 * 15,
};

/** Readable anywhere (Server Components included). */
export function getAccessToken(): string | null {
  return cookies().get(ACCESS)?.value ?? null;
}

/** Server Actions / Route Handlers only (Server Components cannot set cookies). */
export function setAccessToken(token: string): void {
  cookies().set(ACCESS, token, COOKIE_OPTS);
}
