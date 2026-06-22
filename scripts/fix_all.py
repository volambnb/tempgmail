from pathlib import Path

auth = Path("apps/api/src/auth.ts").read_text(encoding="utf-8")
if "import type { Hono }" in auth and auth.index("import type { Hono }") > 200:
    auth = auth.replace("\nimport type { Hono } from \"hono\";\n", "\n")
    if not auth.startswith("import type { Hono }"):
        auth = "import type { Hono } from \"hono\";\n" + auth
    Path("apps/api/src/auth.ts").write_text(auth, encoding="utf-8")

stripe = Path("apps/api/src/stripe.ts").read_text(encoding="utf-8")
if "import type { Hono }" in stripe:
    stripe = stripe.replace("\nimport type { Hono } from \"hono\";\n", "\n")
    stripe = stripe.replace("\nimport { getUserFromRequest } from \"./auth\";\n", "\n")
    if not stripe.startswith("import type { Hono }"):
        stripe = "import type { Hono } from \"hono\";\nimport { getUserFromRequest } from \"./auth\";\n" + stripe
    Path("apps/api/src/stripe.ts").write_text(stripe, encoding="utf-8")

app = '''import { useCallback, useEffect, useState } from "react";
import type { MailboxResp } from "./lib/api";
import { api, mailboxKey } from "./lib/api";
import { Inbox } from "./components/Inbox";
import { Toolbar } from "./components/Toolbar";

const HIST = "tempgmail:history";
const CUR = "tempgmail:current";

type User = { email: string; premium: boolean } | null;

export default function App() {
  const [mailbox, setMailbox] = useState<MailboxResp | null>(() => {
    try { const s = localStorage.getItem(CUR); return s ? JSON.parse(s) : null; } catch { return null; }
  });
  const [history, setHistory] = useState<MailboxResp[]>(() => {
    try { return JSON.parse(localStorage.getItem(HIST) ?? "[]"); } catch { return []; }
  });
  const [turnstileToken, setTurnstileToken] = useState("dev-bypass");
  const [user, setUser] = useState<User>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [customDomain, setCustomDomain] = useState("");

  const refreshUser = useCallback(async () => {
    try {
      const me = await api<{ user: User }>("/api/auth/me");
      setUser(me.user);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => { void refreshUser(); }, [refreshUser]);

  const persist = useCallback((m: MailboxResp) => {
    setMailbox(m);
    localStorage.setItem(CUR, JSON.stringify(m));
    setHistory((h) => {
      const next = [m, ...h.filter((x) => x.address !== m.address)].slice(0, 20);
      localStorage.setItem(HIST, JSON.stringify(next));
      return next;
    });
  }, []);

  const createDomain = async () => {
    const m = await api<MailboxResp>("/api/mailbox", { method: "POST", body: JSON.stringify({ turnstileToken }) });
    persist(m);
  };
  const createGmail = async () => {
    const m = await api<MailboxResp>("/api/gmail-mailbox", { method: "POST", body: JSON.stringify({ turnstileToken }) });
    persist(m);
  };

  const login = async () => {
    await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email: authEmail, password: authPassword }) });
    await refreshUser();
  };
  const register = async () => {
    await api("/api/auth/register", { method: "POST", body: JSON.stringify({ email: authEmail, password: authPassword }) });
    await refreshUser();
  };
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    setUser(null);
  };
  const checkout = async () => {
    const { url } = await api<{ url: string }>("/api/stripe/checkout", { method: "POST" });
    window.location.href = url;
  };
  const addDomain = async () => {
    const res = await api<{ domain: string; verifyToken: string }>("/api/domains", {
      method: "POST",
      body: JSON.stringify({ domain: customDomain }),
    });
    alert(`Add TXT: tempgmail-verify=${res.verifyToken}`);
  };
  const verifyDomain = async () => {
    await api(`/api/domains/${encodeURIComponent(customDomain)}/verify`, { method: "POST" });
    alert("Domain marked verified (manual DNS check in MVP)");
  };

  const key = mailbox ? mailboxKey(mailbox) : "";

  return (
    <div className="app">
      <header className="hero">
        <h1>TempGmail</h1>
        <p>Disposable inbox on oegmail.store or Gmail +alias</p>
      </header>
      <section className="panel auth">
        {user ? (
          <p>{user.email} {user.premium ? "(Premium)" : ""} <button type="button" onClick={logout}>Logout</button> {!user.premium && <button type="button" onClick={checkout}>Upgrade</button>}</p>
        ) : (
          <div className="auth-row">
            <input placeholder="email" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} />
            <input placeholder="password" type="password" value={authPassword} onChange={(e) => setAuthPassword(e.target.value)} />
            <button type="button" onClick={login}>Login</button>
            <button type="button" onClick={register}>Register</button>
          </div>
        )}
      </section>
      <section className="panel">
        <div className="addr-row">
          <input readOnly value={mailbox?.address ?? "No address yet"} className="addr" />
          {mailbox && <Toolbar mailbox={mailbox} mailboxKey={key} onDeleted={() => { setMailbox(null); localStorage.removeItem(CUR); }} />}
        </div>
        <div className="actions">
          <button type="button" onClick={createDomain}>Generate @oegmail.store</button>
          <button type="button" onClick={createGmail}>Gmail Generator</button>
          <label className="ts">Turnstile token <input value={turnstileToken} onChange={(e) => setTurnstileToken(e.target.value)} /></label>
        </div>
        {user?.premium && (
          <div className="domain-row">
            <input placeholder="yourdomain.com" value={customDomain} onChange={(e) => setCustomDomain(e.target.value)} />
            <button type="button" onClick={addDomain}>Add domain</button>
            <button type="button" onClick={verifyDomain}>Verify</button>
          </div>
        )}
        {mailbox && <Inbox mailboxKey={key} address={mailbox.address} />}
        {history.length > 0 && (
          <details className="hist">
            <summary>History</summary>
            <ul>{history.map((h) => (
              <li key={h.address}><button type="button" onClick={() => persist(h)}>{h.address}</button></li>
            ))}</ul>
          </details>
        )}
      </section>
    </div>
  );
}
'''
Path("apps/web/src/App.tsx").write_text(app, encoding="utf-8")

routes = Path("apps/api/src/routes.ts").read_text(encoding="utf-8")
if "isPremium" not in routes:
    routes = routes.replace('import { registerAuthRoutes } from "./auth";', 'import { getUserFromRequest, isPremium, registerAuthRoutes } from "./auth";')
old = """  app.post(\"/api/domains\", async (c) => {
    const { domain } = await c.req.json();
    if (!domain) return c.json({ error: \"invalid\" }, 400);
"""
new = """  app.post(\"/api/domains\", async (c) => {
    const u = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(u)) return c.json({ error: \"premium_required\" }, 403);
    const { domain } = await c.req.json();
    if (!domain) return c.json({ error: \"invalid\" }, 400);
"""
if old in routes:
    routes = routes.replace(old, new)
Path("apps/api/src/routes.ts").write_text(routes, encoding="utf-8")

readme = """# TempGmail

Monorepo for a disposable inbox service on Cloudflare Workers.

## Apps

- `apps/api` — Hono API, Durable Object mailbox state, Gmail polling, auth, Stripe hooks
- `apps/email-worker` — Cloudflare Email Worker (PostalMime parse, R2 attachments, forward)
- `apps/web` — Vite + React UI (inbox, QR, history, premium domain UI)
- `packages/shared` — shared TypeScript types

## Local dev

```bash
npm install
npm run dev:api
npm run dev:web
```

Set `VITE_API_URL` to your API origin when the web app is on another host.

## Cloudflare setup

1. Create D1 database, R2 bucket, KV namespace, and bind them in `apps/api/wrangler.toml`.
2. Deploy `apps/api` first (exports `MailboxDO`).
3. Deploy `apps/email-worker` with `script_name` pointing at the API worker.
4. Enable **Email Routing** catch-all for `oegmail.store` (and premium domains) to the email worker.
5. Add secrets: `TURNSTILE_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BETTER_AUTH_SECRET`, optional `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.

## Migrations

Apply SQL in `migrations/` to D1 (`0001_init.sql`, `0002_auth_stripe.sql`).

## Tests

```bash
npm test
npm run build
```
"""
Path("README.md").write_text(readme, encoding="utf-8")
print("fixes ok")
