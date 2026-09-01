import { NextResponse } from "next/server";

export function POST(request: Request) {
  const res = NextResponse.redirect(new URL("/login", request.url), { status: 303 });
  res.cookies.delete("eraj_access");
  return res;
}
