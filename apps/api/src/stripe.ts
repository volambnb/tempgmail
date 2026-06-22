import type { Hono } from "hono";
import { getUserFromRequest } from "./auth";
import type { Env } from "./env";

const PREMIUM_MS = 30 * 24 * 60 * 60 * 1000;

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload)));
}

async function verifyStripeSignature(secret: string, sig: string, raw: string): Promise<boolean> {
  const parts = Object.fromEntries(sig.split(",").map((p) => {
    const [k, v] = p.split("=");
    return [k, v];
  }));
  if (!parts.t || !parts.v1) return false;
  const expected = await hmacSha256(secret, `${parts.t}.${raw}`);
  return expected === parts.v1;
}

export async function createCheckoutSession(env: Env, userId: string, email: string, origin: string): Promise<string | null> {
  if (!env.STRIPE_SECRET_KEY) return null;
  const body = new URLSearchParams({
    mode: "subscription",
    success_url: `${origin}/?premium=1`,
    cancel_url: `${origin}/?premium=0`,
    "line_items[0][price_data][currency]": "usd",
    "line_items[0][price_data][product_data][name]": "TempGmail Premium",
    "line_items[0][price_data][unit_amount]": "499",
    "line_items[0][price_data][recurring][interval]": "month",
    "line_items[0][quantity]": "1",
    customer_email: email,
    "metadata[user_id]": userId,
  });
  const res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = (await res.json()) as { url?: string };
  return data.url ?? null;
}

export async function handleStripeWebhook(env: Env, req: Request): Promise<Response> {
  if (!env.STRIPE_WEBHOOK_SECRET) return new Response("no webhook secret", { status: 500 });
  const sig = req.headers.get("stripe-signature") ?? "";
  const raw = await req.text();
  let event: { type?: string; data?: { object?: { metadata?: { user_id?: string } } } };
  try {
    event = JSON.parse(raw);
  } catch {
    return new Response("bad json", { status: 400 });
  }
  if (env.STRIPE_WEBHOOK_SECRET.startsWith("whsec_")) {
    if (!(await verifyStripeSignature(env.STRIPE_WEBHOOK_SECRET, sig, raw))) {
      return new Response("bad signature", { status: 400 });
    }
  }
  if (event.type === "checkout.session.completed") {
    const uid = event.data?.object?.metadata?.user_id;
    if (uid) {
      const until = Date.now() + PREMIUM_MS;
      await env.DB.prepare("UPDATE users SET premium_until = ? WHERE id = ?").bind(until, uid).run();
    }
  }
  return new Response(JSON.stringify({ received: true }), { headers: { "content-type": "application/json" } });
}

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
