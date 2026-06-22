import { useCallback, useEffect, useRef, useState } from "react";
import type { MailboxResp } from "./lib/api";
import { api, mailboxKey } from "./lib/api";
import { Inbox } from "./components/Inbox";
import { Toolbar } from "./components/Toolbar";

const HIST = "tempgmail:history";
const CUR = "tempgmail:current";
const DOMAINS = "tempgmail:domains";

type User = { email: string; premium: boolean } | null;

declare global {
  interface Window {
    onTurnstileSuccess?: (token: string) => void;
    onTurnstileExpired?: () => void;
    turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => string; reset: (id?: string) => void };
  }
}

export default function App() {
  const [mailbox, setMailbox] = useState<MailboxResp | null>(() => {
    try { const s = localStorage.getItem(CUR); return s ? JSON.parse(s) : null; } catch { return null; }
  });
  const [history, setHistory] = useState<MailboxResp[]>(() => {
    try { return JSON.parse(localStorage.getItem(HIST) ?? "[]"); } catch { return []; }
  });
  const [turnstileSiteKey, setTurnstileSiteKey] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("dev-bypass");
  const [turnstilePassed, setTurnstilePassed] = useState(false);
  const turnstileRef = useRef<HTMLDivElement | null>(null);
  const turnstileWidget = useRef("");
  const [user, setUser] = useState<User>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [manualLocal, setManualLocal] = useState("");
  const [selectedDomain, setSelectedDomain] = useState("stockai.store");
  const [domains, setDomains] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(DOMAINS) ?? "[\"stockai.store\"]"); } catch { return ["stockai.store"]; }
  });
  const [customDomain, setCustomDomain] = useState("");
  const [customOpen, setCustomOpen] = useState(false);
  const [customTxt, setCustomTxt] = useState("");
  const [customVerified, setCustomVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const refreshUser = useCallback(async () => {
    try {
      const me = await api<{ user: User }>("/api/auth/me");
      setUser(me.user);
    } catch {
      setUser(null);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const rows = await api<MailboxResp[]>("/api/history");
      if (rows.length) {
        setHistory(rows);
        localStorage.setItem(HIST, JSON.stringify(rows));
      }
    } catch {
      // Keep local history when the API is not reachable.
    }
  }, []);

  useEffect(() => { void refreshUser(); void loadHistory(); }, [refreshUser, loadHistory]);
  useEffect(() => {
    api<{ turnstileSiteKey: string }>("/api/config")
      .then((cfg) => {
        setTurnstileSiteKey(cfg.turnstileSiteKey);
        setTurnstilePassed(!cfg.turnstileSiteKey || Boolean((cfg as { turnstileVerified?: boolean }).turnstileVerified));
        if (cfg.turnstileSiteKey) setTurnstileToken("");
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    window.onTurnstileSuccess = (token: string) => setTurnstileToken(token);
    window.onTurnstileExpired = () => setTurnstileToken("");
    return () => {
      delete window.onTurnstileSuccess;
      delete window.onTurnstileExpired;
    };
  }, []);
  useEffect(() => {
    if (!turnstileSiteKey || turnstileWidget.current) return;
    const id = window.setInterval(() => {
      if (!turnstileRef.current || turnstileWidget.current || !window.turnstile) return;
      turnstileWidget.current = window.turnstile.render(turnstileRef.current, {
        sitekey: turnstileSiteKey,
        callback: window.onTurnstileSuccess,
        "expired-callback": window.onTurnstileExpired,
        "error-callback": window.onTurnstileExpired,
      });
      window.clearInterval(id);
    }, 200);
    return () => window.clearInterval(id);
  }, [turnstileSiteKey]);
  useEffect(() => {
    if (!turnstileSiteKey || !turnstileToken || turnstilePassed) return;
    api<{ ok: boolean }>("/api/turnstile/verify", {
      method: "POST",
      body: JSON.stringify({ token: turnstileToken }),
    })
      .then(() => setTurnstilePassed(true))
      .catch(() => {
        setTurnstileToken("");
        window.turnstile?.reset(turnstileWidget.current);
      });
  }, [turnstileSiteKey, turnstileToken, turnstilePassed]);
  useEffect(() => {
    if (mailbox?.mode === "domain") {
      const [local, domain] = mailbox.address.split("@");
      setManualLocal(local ?? "");
      if (domain) setSelectedDomain(domain);
    }
  }, [mailbox]);

  const persist = useCallback((m: MailboxResp) => {
    setMailbox(m);
    localStorage.setItem(CUR, JSON.stringify(m));
    setHistory((h) => {
      const next = [m, ...h.filter((x) => x.address !== m.address)].slice(0, 20);
      localStorage.setItem(HIST, JSON.stringify(next));
      return next;
    });
  }, []);

  const cleanManualLocal = () => manualLocal.toLowerCase().trim().replace(/^@+/, "");
  const rememberDomain = useCallback((domain: string) => {
    const clean = domain.toLowerCase().trim();
    if (!clean) return;
    setDomains((items) => {
      const next = Array.from(new Set(["stockai.store", ...items, clean]));
      localStorage.setItem(DOMAINS, JSON.stringify(next));
      return next;
    });
    setSelectedDomain(clean);
  }, []);
  const resetTurnstile = () => {
    if (!turnstileSiteKey) return;
    setTurnstileToken("");
    window.turnstile?.reset(turnstileWidget.current);
  };

  const createDomain = async (domain?: string, local?: string) => {
    if (turnstileSiteKey && !turnstilePassed) {
      setNotice("Complete the Turnstile check first.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const m = await api<MailboxResp>("/api/mailbox", {
        method: "POST",
        body: JSON.stringify({ turnstileToken, domain, local: local || undefined }),
      });
      persist(m);
      rememberDomain(m.address.split("@")[1] ?? "stockai.store");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Cannot create mailbox.");
    } finally {
      setBusy(false);
    }
  };
  const createGmail = async () => {
    if (turnstileSiteKey && !turnstilePassed) {
      setNotice("Complete the Turnstile check first.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const m = await api<MailboxResp>("/api/gmail-mailbox", { method: "POST", body: JSON.stringify({ turnstileToken }) });
      persist(m);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Cannot create Gmail alias.");
    } finally {
      setBusy(false);
    }
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
    if (!customDomain.trim()) {
      setNotice("Enter a custom domain first.");
      return;
    }
    setBusy(true);
    setNotice("");
    setCustomVerified(false);
    try {
      const res = await api<{ domain: string; verifyTxt: string; note?: string }>("/api/domains", {
        method: "POST",
        body: JSON.stringify({ domain: customDomain }),
      });
      setCustomDomain(res.domain);
      rememberDomain(res.domain);
      setCustomTxt(res.verifyTxt);
      setNotice(`Add TXT record to ${res.domain}, then click Verify.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Cannot add custom domain.");
    } finally {
      setBusy(false);
    }
  };
  const verifyDomain = async () => {
    if (!customDomain.trim()) {
      setNotice("Enter a custom domain first.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const res = await api<{ status: string; expectedTxt: string }>(`/api/domains/${encodeURIComponent(customDomain)}/verify`, { method: "POST" });
      setCustomTxt(res.expectedTxt);
      setCustomVerified(res.status === "verified");
      if (res.status === "verified") rememberDomain(customDomain);
      setNotice(res.status === "verified" ? `${customDomain} verified.` : `Status: ${res.status}`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Cannot verify custom domain yet.");
    } finally {
      setBusy(false);
    }
  };
  const key = mailbox ? mailboxKey(mailbox) : "";
  const createFromComposer = () => {
    const domain = selectedDomain === "stockai.store" ? undefined : selectedDomain;
    return createDomain(domain, cleanManualLocal());
  };

  if (turnstileSiteKey && !turnstilePassed) {
    return (
      <div className="gate starfield">
        <section className="gate-card">
          <h1>Verify access</h1>
          <p>Complete the check to open your temporary inbox.</p>
          <div className="turnstile-wrap">
            <div ref={turnstileRef} />
          </div>
          {!turnstileToken && <span className="gate-muted">Waiting for verification...</span>}
        </section>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="hero starfield">
        <div className="hero-inner">
          <h1>Your Temporary Email Address</h1>
          <p>Free temporary email addresses to protect your privacy online.</p>
          <section className="mailbox-card" aria-label="Temporary email address">
            <div className="composer">
              <div className="composer-input">
                <input
                  value={manualLocal}
                  onChange={(e) => setManualLocal(e.target.value)}
                  placeholder="set email id manually"
                  aria-label="Set email id manually"
                />
                <select value={selectedDomain} onChange={(e) => setSelectedDomain(e.target.value)} aria-label="Select domain">
                  {domains.map((domain) => <option key={domain} value={domain}>@{domain}</option>)}
                </select>
              </div>
              <button type="button" onClick={() => void createDomain(selectedDomain === "stockai.store" ? undefined : selectedDomain)} disabled={busy}>
                Random
              </button>
              <button type="button" onClick={() => void createFromComposer()} disabled={busy}>
                Create
              </button>
              <button
                type="button"
                className="copy-square"
                onClick={() => mailbox && navigator.clipboard.writeText(mailbox.address)}
                aria-label="Copy email address"
                disabled={!mailbox}
              >
                <span>Copy</span>
              </button>
            </div>
            <div className="quick-actions">
              <button type="button" className="tool-btn" onClick={() => mailbox && window.location.reload()} disabled={!mailbox}>
                Refresh
              </button>
              {mailbox && <Toolbar mailbox={mailbox} mailboxKey={key} premium={Boolean(user?.premium)} onDeleted={() => { setMailbox(null); localStorage.removeItem(CUR); }} />}
            </div>
            <div className="generator-actions">
              <button type="button" className="feature-btn" onClick={createGmail} disabled={busy}>
                Gmail Generator <b>NEW</b>
              </button>
              <button
                type="button"
                className="feature-btn"
                onClick={() => setCustomOpen((value) => !value)}
                disabled={busy}
              >
                Add Custom Domain <b>NEW</b>
              </button>
            </div>
            {customOpen && (
              <div className="custom-card">
                <div className="custom-row">
                  <input
                    value={customDomain}
                    onChange={(e) => {
                      setCustomDomain(e.target.value);
                      setCustomVerified(false);
                    }}
                    placeholder="yourdomain.com"
                  />
                  <button type="button" onClick={addDomain} disabled={busy}>Get TXT</button>
                  <button type="button" onClick={verifyDomain} disabled={busy}>Verify</button>
                  <button type="button" onClick={() => void createDomain(customDomain, cleanManualLocal())} disabled={busy || !customVerified}>
                    Generate
                  </button>
                </div>
                {customTxt && (
                  <div className="dns-box">
                    <span>TXT</span>
                    <code>{customTxt}</code>
                    <button type="button" onClick={() => navigator.clipboard.writeText(customTxt)}>Copy TXT</button>
                  </div>
                )}
              </div>
            )}
            {notice && <div className="notice" role="status">{notice}</div>}
          </section>
        </div>
      </header>

      <main className="content">
        {user && <section className="auth-strip">
            <p>{user.email} {user.premium ? "(Premium)" : ""} <button type="button" onClick={logout}>Logout</button> {!user.premium && <button type="button" onClick={checkout}>Upgrade</button>}</p>
        </section>}
        <section className="panel">
          <details className="tools">
            <summary>Tools</summary>
            {!turnstileSiteKey && <label className="ts">Turnstile token <input value={turnstileToken} onChange={(e) => setTurnstileToken(e.target.value)} /></label>}
            <button type="button" onClick={() => void loadHistory()}>Sync history</button>
            <span>Language: EN</span>
          </details>
          {mailbox ? <Inbox mailboxKey={key} address={mailbox.address} /> : (
            <div className="inbox empty-shell">
              <div className="inbox-title"><span className="mail-icon">Mail</span><h2>Inbox</h2><span className="pill">0 New</span></div>
              <div className="empty"><div className="empty-icon">Mail</div><strong>Your inbox is empty</strong><p>Generate an address to start receiving emails.</p></div>
            </div>
          )}
          {history.length > 0 && (
            <details className="hist">
              <summary>History</summary>
              <ul>{history.map((h) => (
                <li key={h.address}><button type="button" onClick={() => persist(h)}>{h.address}</button></li>
              ))}</ul>
            </details>
          )}
        </section>
      </main>
    </div>
  );
}
