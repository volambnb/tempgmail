import type { Hono } from "hono";
import type { Env } from "./env";

const COOKIE = "tm_auth";
const SESSION_MS = 30 * 24 * 60 * 60 * 1000;

export type AuthUser = { id: string; email: string; premiumUntil: number | null };

function b64(bytes: ArrayBuffer): string {
  const u8 = new Uint8Array(bytes);
  let s = "";
  for (const b of u8) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return b64(buf);
}

export async function hashPassword(password: string, secret: string): Promise<string> {
  return sha256(`${secret}:${password}`);
}

export function parseCookies(req: Request): Record<string, string> {
  const out: Record<string, string> = {};
  const raw = req.headers.get("Cookie") ?? "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 1) continue;
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

export function authCookie(sessionId: string, maxAgeSec: number): string {
  return `${COOKIE}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeSec}`;
}

export function clearAuthCookie(): string {
  return `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}

export async function getUserFromRequest(env: Env, req: Request): Promise<AuthUser | null> {
  const sid = parseCookies(req)[COOKIE];
  if (!sid) return null;
  const row = await env.DB.prepare(
    "SELECT u.id, u.email, u.premium_until FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ? AND s.expires_at > ?",
  )
    .bind(sid, Date.now())
    .first<{ id: string; email: string; premium_until: number | null }>();
  if (!row) return null;
  return { id: row.id, email: row.email, premiumUntil: row.premium_until };
}

export async function createSession(env: Env, userId: string): Promise<string> {
  const id = crypto.randomUUID();
  const exp = Date.now() + SESSION_MS;
  await env.DB.prepare("INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?,?,?,?)")
    .bind(id, userId, exp, Date.now())
    .run();
  return id;
}

export async function destroySession(env: Env, req: Request): Promise<void> {
  const sid = parseCookies(req)[COOKIE];
  if (!sid) return;
  await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(sid).run();
}

export function isPremium(user: AuthUser | null): boolean {
  return Boolean(user?.premiumUntil && user.premiumUntil > Date.now());
}


export function registerAuthRoutes(app: Hono<{ Bindings: import("./env").Env }>) {
  app.post("/api/auth/register", async (c) => {
    const { email, password } = await c.req.json();
    if (!email || !password || String(password).length < 8) return c.json({ error: "invalid" }, 400);
    const id = crypto.randomUUID();
    const hash = await hashPassword(String(password), c.env.BETTER_AUTH_SECRET || "dev");
    try {
      await c.env.DB.prepare("INSERT INTO users (id,email,password_hash,created_at) VALUES (?,?,?,?)")
        .bind(id, String(email).toLowerCase(), hash, Date.now()).run();
    } catch {
      return c.json({ error: "exists" }, 409);
    }
    const sid = await createSession(c.env, id);
    return c.json({ ok: true }, { headers: { "Set-Cookie": authCookie(sid, 2592000) } });
  });
  app.post("/api/auth/login", async (c) => {
    const { email, password } = await c.req.json();
    const row = await c.env.DB.prepare("SELECT id, password_hash FROM users WHERE email = ?")
      .bind(String(email).toLowerCase()).first<{ id: string; password_hash: string }>();
    if (!row) return c.json({ error: "invalid" }, 401);
    const hash = await hashPassword(String(password), c.env.BETTER_AUTH_SECRET || "dev");
    if (hash !== row.password_hash) return c.json({ error: "invalid" }, 401);
    const sid = await createSession(c.env, row.id);
    return c.json({ ok: true }, { headers: { "Set-Cookie": authCookie(sid, 2592000) } });
  });
  app.post("/api/auth/logout", async (c) => {
    await destroySession(c.env, c.req.raw);
    return c.json({ ok: true }, { headers: { "Set-Cookie": clearAuthCookie() } });
  });
  app.get("/api/auth/me", async (c) => {
    const u = await getUserFromRequest(c.env, c.req.raw);
    if (!u) return c.json({ user: null });
    return c.json({ user: { email: u.email, premium: isPremium(u) } });
  });
}
