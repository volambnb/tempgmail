from pathlib import Path
ROOT = Path(r"D:\codex\tempgmail")
auth = ROOT / "apps/api/src/auth.ts"
text = auth.read_text(encoding="utf-8")
if "registerAuthRoutes" not in text:
    extra = '''

import type { Hono } from "hono";
import { authCookie, clearAuthCookie, createSession, destroySession, getUserFromRequest, hashPassword, isPremium } from "./auth";

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
'''
    # fix: we need to append register function without self-import - rewrite file
    base = text.rstrip() + '''

import type { Hono } from "hono";

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
'''
    auth.write_text(base, encoding="utf-8")
    print("auth routes ok")

stripe = ROOT / "apps/api/src/stripe.ts"
st = stripe.read_text(encoding="utf-8")
if "registerStripeRoutes" not in st:
    st = st.rstrip() + '''

import type { Hono } from "hono";
import { getUserFromRequest } from "./auth";
import { createCheckoutSession, handleStripeWebhook } from "./stripe";

export function registerStripeRoutes(app: Hono<{ Bindings: import("./env").Env }>) {
  app.post("/api/stripe/checkout", async (c) => {
    const u = await getUserFromRequest(c.env, c.req.raw);
    if (!u) return c.json({ error: "auth" }, 401);
    const origin = c.req.header("Origin") || "http://localhost:5173";
    const url = await createCheckoutSession(c.env, u.id, u.email, origin);
    if (!url) return c.json({ error: "stripe_not_configured" }, 503);
    return c.json({ url });
  });
  app.post("/api/stripe/webhook", async (c) => handleStripeWebhook(c.env, c.req.raw));
}
'''
    # remove self-import in appended block
    st = stripe.read_text(encoding="utf-8").rstrip() + '''

import type { Hono } from "hono";
import { getUserFromRequest } from "./auth";

export function registerStripeRoutes(app: Hono<{ Bindings: import("./env").Env }>) {
  app.post("/api/stripe/checkout", async (c) => {
    const u = await getUserFromRequest(c.env, c.req.raw);
    if (!u) return c.json({ error: "auth" }, 401);
    const origin = c.req.header("Origin") || "http://localhost:5173";
    const url = await createCheckoutSession(c.env, u.id, u.email, origin);
    if (!url) return c.json({ error: "stripe_not_configured" }, 503);
    return c.json({ url });
  });
  app.post("/api/stripe/webhook", async (c) => handleStripeWebhook(c.env, c.req.raw));
}
'''
    stripe.write_text(st, encoding="utf-8")
    print("stripe routes ok")
