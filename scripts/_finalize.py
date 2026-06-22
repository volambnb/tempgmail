from pathlib import Path
ROOT = Path(r"D:\codex\tempgmail")

routes = r'''import { Hono } from "hono";
import type { Env } from "./env";
import { allowRate, randomLocal, sessionIdFromRequest, verifyTurnstile } from "./security";
import { dotify, pickBackingGmail } from "./gmail";
import { getUserFromRequest, isPremium, registerAuthRoutes } from "./auth";
import { registerStripeRoutes } from "./stripe";

const DEFAULT_DOMAIN = "oegmail.store";
const TTL_MS = 3600_000;

function sessionCookie(id: string): string {
  return `tm_session=${encodeURIComponent(id)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000`;
}

function withSession(c: { header: (n: string, v: string) => void }, sid: string) {
  c.header("Set-Cookie", sessionCookie(sid));
}

async function recordHistory(
  env: Env,
  sid: string,
  mailboxKey: string,
  display: string,
  kind: "domain" | "gmail",
) {
  await env.DB.prepare(
    "INSERT INTO mailbox_history (id, session_id, mailbox_key, display_address, kind, created_at) VALUES (?,?,?,?,?,?)",
  )
    .bind(crypto.randomUUID(), sid, mailboxKey, display, kind, Date.now())
    .run();
}

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();

  async function guard(c: any) {
    const body = await c.req.json().catch(() => ({}));
    const ip = c.req.header("CF-Connecting-IP") ?? "0.0.0.0";
    const token = body.turnstileToken as string | undefined;
    if (c.env.TURNSTILE_SECRET && !(await verifyTurnstile(token, ip, c.env))) {
      return { ok: false as const, res: c.json({ error: "captcha" }, 403) };
    }
    if (!(await allowRate(c.env, ip))) {
      return { ok: false as const, res: c.json({ error: "rate" }, 429) };
    }
    return { ok: true as const, body, ip };
  }

  function mailboxStub(env: Env, key: string) {
    return env.MAILBOX.get(env.MAILBOX.idFromName(key.toLowerCase()));
  }

  async function assertMailboxOwner(c: any, key: string, mode: "domain" | "gmail") {
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (mode === "domain") {
      const row = await c.env.DB.prepare("SELECT session_id, user_id FROM mailboxes WHERE address = ?")
        .bind(key.toLowerCase())
        .first<{ session_id: string | null; user_id: string | null }>();
      if (!row) return false;
      if (user && row.user_id === user.id) return true;
      return row.session_id === sid;
    }
    const row = await c.env.DB.prepare("SELECT session_id, user_id FROM gmail_mailboxes WHERE alias_key = ?")
      .bind(key)
      .first<{ session_id: string | null; user_id: string | null }>();
    if (!row) return false;
    if (user && row.user_id === user.id) return true;
    return row.session_id === sid;
  }

  app.post("/api/mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const domain = c.env.DEFAULT_DOMAIN || DEFAULT_DOMAIN;
    const address = `${randomLocal()}@${domain}`.toLowerCase();
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO mailboxes (address, domain, session_id, user_id, expires_at, created_at) VALUES (?,?,?,?,?,?)",
    )
      .bind(address, domain, sid, user?.id ?? null, expiresAt, Date.now())
      .run();
    const stub = mailboxStub(c.env, address);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    await recordHistory(c.env, sid, address, address, "domain");
    withSession(c, sid);
    return c.json({ address, expiresAt, mode: "domain" });
  });

  app.post("/api/gmail-mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const account = pickBackingGmail(c.env);
    if (!account) return c.json({ error: "no_gmail_backend" }, 503);
    const tag = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const display = `${dotify(account.local)}+${tag}@gmail.com`;
    const aliasKey = `${account.email}#${tag}`;
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO gmail_mailboxes (alias_key, display_address, backing_account, plus_tag, session_id, user_id, expires_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
    )
      .bind(aliasKey, display, account.email, tag, sid, user?.id ?? null, expiresAt, Date.now())
      .run();
    const stub = mailboxStub(c.env, aliasKey);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    await stub.fetch("https://do/poll-start", {
      method: "POST",
      body: JSON.stringify({ account: account.email, tag, aliasKey }),
    });
    await recordHistory(c.env, sid, aliasKey, display, "gmail");
    withSession(c, sid);
    return c.json({ address: display, aliasKey, expiresAt, mode: "gmail" });
  });

  app.get("/api/mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    return mailboxStub(c.env, key).fetch("https://do/list");
  });

  app.get("/api/gmail-mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    return mailboxStub(c.env, key).fetch("https://do/list");
  });

  app.post("/api/mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    const { id } = await c.req.json();
    await mailboxStub(c.env, key).fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.post("/api/gmail-mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    const { id } = await c.req.json();
    await mailboxStub(c.env, key).fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.delete("/api/mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    await mailboxStub(c.env, key).fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM mailboxes WHERE address = ?").bind(key.toLowerCase()).run();
    return c.json({ ok: true });
  });

  app.delete("/api/gmail-mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    await mailboxStub(c.env, key).fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM gmail_mailboxes WHERE alias_key = ?").bind(key).run();
    return c.json({ ok: true });
  });

  app.post("/api/mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const { forwardTo } = await c.req.json();
    await c.env.DB.prepare("UPDATE mailboxes SET forward_to = ? WHERE address = ?")
      .bind(forwardTo || null, key.toLowerCase())
      .run();
    return c.json({ ok: true });
  });

  app.post("/api/gmail-mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const { forwardTo } = await c.req.json();
    await c.env.DB.prepare("UPDATE gmail_mailboxes SET forward_to = ? WHERE alias_key = ?")
      .bind(forwardTo || null, key)
      .run();
    return c.json({ ok: true });
  });

  app.get("/api/attachments/*", async (c) => {
    const key = c.req.path.replace(/^\/api\/attachments\//, "");
    const obj = await c.env.ATTACHMENTS.get(key);
    if (!obj) return c.json({ error: "not_found" }, 404);
    const headers = new Headers();
    obj.writeHttpMetadata(headers);
    headers.set("cache-control", "private, max-age=3600");
    return new Response(obj.body, { headers });
  });

  app.get("/api/history", async (c) => {
    const sid = sessionIdFromRequest(c.req.raw);
    withSession(c, sid);
    const rows = await c.env.DB.prepare(
      "SELECT mailbox_key, display_address, kind, created_at FROM mailbox_history WHERE session_id = ? ORDER BY created_at DESC LIMIT 30",
    )
      .bind(sid)
      .all<{ mailbox_key: string; display_address: string; kind: string; created_at: number }>();
    const out = [];
    for (const r of rows.results ?? []) {
      if (r.kind === "gmail") {
        const g = await c.env.DB.prepare("SELECT expires_at FROM gmail_mailboxes WHERE alias_key = ?")
          .bind(r.mailbox_key)
          .first<{ expires_at: number }>();
        if (!g) continue;
        out.push({ address: r.display_address, aliasKey: r.mailbox_key, expiresAt: g.expires_at, mode: "gmail" as const });
      } else {
        const m = await c.env.DB.prepare("SELECT expires_at FROM mailboxes WHERE address = ?")
          .bind(r.mailbox_key)
          .first<{ expires_at: number }>();
        if (!m) continue;
        out.push({ address: r.display_address, expiresAt: m.expires_at, mode: "domain" as const });
      }
    }
    return c.json(out);
  });

  app.post("/api/domains", async (c) => {
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const { domain } = await c.req.json();
    const hostname = String(domain || "").toLowerCase().trim();
    if (!hostname.includes(".")) return c.json({ error: "invalid_domain" }, 400);
    const token = crypto.randomUUID().replace(/-/g, "");
    const sid = sessionIdFromRequest(c.req.raw);
    const id = crypto.randomUUID();
    await c.env.DB.prepare(
      "INSERT INTO domains (id, hostname, owner_session_id, verification_token, status, created_at) VALUES (?,?,?,?,?,?)",
    )
      .bind(id, hostname, sid, token, "pending", Date.now())
      .run();
    return c.json({
      domain: hostname,
      verifyTxt: `tempgmail-verify=${token}`,
      note: "Add this TXT record in Cloudflare DNS, enable Email Routing catch-all for the zone.",
    });
  });

  app.post("/api/domains/:domain/verify", async (c) => {
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const hostname = decodeURIComponent(c.req.param("domain")).toLowerCase();
    const row = await c.env.DB.prepare("SELECT id, verification_token FROM domains WHERE hostname = ?")
      .bind(hostname)
      .first<{ id: string; verification_token: string }>();
    if (!row) return c.json({ error: "not_found" }, 404);
    await c.env.DB.prepare("UPDATE domains SET status = ?, verified_at = ? WHERE id = ?")
      .bind("verified", Date.now(), row.id)
      .run();
    return c.json({ ok: true, status: "verified" });
  });

  registerAuthRoutes(app);
  registerStripeRoutes(app);
  return app;
}
'''

gmail_patch = r'''export async function lookupRefreshToken(env: Env, accountEmail: string): Promise<string | null> {
  const backend = parseBackends(env).find((b) => b.email === accountEmail.toLowerCase());
  return backend?.refreshToken ?? null;
}
'''

(ROOT / "apps/api/src/routes.ts").write_text(routes, encoding="utf-8")

gpath = ROOT / "apps/api/src/gmail.ts"
gt = gpath.read_text(encoding="utf-8")
import re
gt = re.sub(
    r"export async function lookupRefreshToken\(env: Env, accountEmail: string\): Promise<string \| null> \{[\s\S]*?\n\}\n",
    gmail_patch + "\n",
    gt,
    count=1,
)
gpath.write_text(gt, encoding="utf-8")

(ROOT / "apps/api/src/gmail.test.ts").write_text(
    '''import { describe, expect, it } from "vitest";
import { dotify, extractPlusTag } from "./gmail";
import { randomLocal } from "./security";

describe("gmail helpers", () => {
  it("extracts plus tag", () => {
    expect(extractPlusTag("user+abc123@gmail.com")).toBe("abc123");
  });
  it("random local starts with u", () => {
    expect(randomLocal()).toMatch(/^u[a-z0-9]+$/);
  });
  it("dotify keeps chars", () => {
    expect(dotify("abc").replace(/\\./g, "")).toBe("abc");
  });
});
''',
    encoding="utf-8",
)

toolbar = '''import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { MailboxResp } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  mailbox: MailboxResp;
  mailboxKey: string;
  onDeleted: () => void;
  premium?: boolean;
};

export function Toolbar({ mailbox, mailboxKey, onDeleted, premium = false }: Props) {
  const [qr, setQr] = useState("");
  const [fwd, setFwd] = useState("");
  const base = mailbox.mode === "gmail" ? "/api/gmail-mailbox" : "/api/mailbox";

  useEffect(() => {
    QRCode.toDataURL(mailbox.address, { width: 120, margin: 1 }).then(setQr);
  }, [mailbox.address]);

  const copy = async () => {
    await navigator.clipboard.writeText(mailbox.address);
  };

  const del = async () => {
    await api(`${base}/${encodeURIComponent(mailboxKey)}`, { method: "DELETE" });
    onDeleted();
  };

  const saveFwd = async () => {
    if (!premium) return;
    await api(`${base}/${encodeURIComponent(mailboxKey)}/forward`, {
      method: "POST",
      body: JSON.stringify({ forwardTo: fwd || null }),
    });
  };

  return (
    <div className="toolbar">
      <button type="button" onClick={copy}>Copy</button>
      <button type="button" onClick={del}>Delete</button>
      {qr && <img src={qr} alt="QR" className="qr" />}
      {premium ? (
        <label className="fwd">
          Forward to
          <input value={fwd} onChange={(e) => setFwd(e.target.value)} placeholder="you@example.com" />
          <button type="button" onClick={saveFwd}>Save</button>
        </label>
      ) : (
        <span className="fwd muted">Forward (Premium)</span>
      )}
    </div>
  );
}
'''
(ROOT / "apps/web/src/components/Toolbar.tsx").write_text(toolbar, encoding="utf-8")

(ROOT / "apps/api/schema.sql").write_text((ROOT / "migrations/0001_init.sql").read_text(encoding="utf-8") + "\n" + (ROOT / "migrations/0002_auth_stripe.sql").read_text(encoding="utf-8"), encoding="utf-8")

(ROOT / ".env.example").write_text("""# API worker secrets (wrangler secret put)
TURNSTILE_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GMAIL_BACKENDS_JSON=[{"email":"you@gmail.com","refreshToken":"..."}]
BETTER_AUTH_SECRET=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
OPERATOR_GMAIL=

# Web (Vite)
VITE_API_URL=http://127.0.0.1:8787
VITE_TURNSTILE_SITE_KEY=
""", encoding="utf-8")

(ROOT / ".github/workflows/ci.yml").write_text("""name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm test
      - run: npm run build
""", encoding="utf-8")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
if "npm run build" not in readme.split("## Tests")[-1]:
    readme = readme.replace("```bash\nnpm test\nnpm run build\n```", "```bash\nnpm test\nnpm run build\n```")
(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("written")
