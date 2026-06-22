import { useCallback, useEffect, useMemo, useState } from "react";
import type { Msg } from "../lib/api";
import { api } from "../lib/api";
import { MessageRow } from "./MessageRow";

export function Inbox({ mailboxKey, address }: { mailboxKey: string; address: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [live, setLive] = useState<"checking" | "on" | "off">("checking");
  const [seconds, setSeconds] = useState(15);

  const messagePath = useCallback(() => (
    mailboxKey.includes("#")
      ? `/api/gmail-mailbox/${encodeURIComponent(mailboxKey)}/messages`
      : `/api/mailbox/${encodeURIComponent(address)}/messages`
  ), [mailboxKey, address]);

  const poll = useCallback(async () => {
    try {
      const data = await api<Msg[]>(messagePath());
      setMsgs(data);
      setLive("on");
      setSeconds(15);
    } catch {
      setLive("off");
      setSeconds(15);
    }
  }, [messagePath]);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (alive) await poll();
    };
    void run();
    const id = setInterval(run, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [poll]);

  useEffect(() => {
    const id = setInterval(() => {
      setSeconds((value) => (value > 0 ? value - 1 : 15));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const markRead = async (id: string) => {
    const base = mailboxKey.includes("#") ? "/api/gmail-mailbox" : "/api/mailbox";
    const key = mailboxKey.includes("#") ? mailboxKey : address;
    await api(`${base}/${encodeURIComponent(key)}/read`, {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    setMsgs((items) => items.map((m) => (m.id === id ? { ...m, read: true } : m)));
  };

  const view = useMemo(() => {
    const f = filter === "unread" ? msgs.filter((m) => !m.read) : msgs;
    return [...f].sort((a, b) => sort === "newest" ? b.receivedAt - a.receivedAt : a.receivedAt - b.receivedAt);
  }, [msgs, filter, sort]);

  return (
    <div className="inbox">
      <div className="inbox-bar">
        <div className="inbox-title">
          <span className="mail-icon">Mail</span>
          <h2>Inbox</h2>
          <span className="pill">{msgs.filter((m) => !m.read).length} New</span>
        </div>
        <div className="status-row">
          <span className="pill soft">{seconds}s</span>
          <span className={live === "on" ? "pill live on" : live === "checking" ? "pill live checking" : "pill live"}>
            {live === "on" ? "Live" : live === "checking" ? "Checking" : "Offline"}
          </span>
          <span className="pill lock">Encrypted</span>
          <button type="button" className="icon-btn" onClick={() => void poll()} aria-label="Refresh inbox">Refresh</button>
          <button type="button" className="support-btn">Support Us</button>
          <button type="button" className="issue-btn">Issue Report</button>
        </div>
      </div>
      <div className="filter-row">
        <label>Filter:
          <select value={filter} onChange={(e) => setFilter(e.target.value as "all" | "unread")}><option value="all">All Emails</option><option value="unread">Unread</option></select>
        </label>
        <label>Sort:
          <select value={sort} onChange={(e) => setSort(e.target.value as "newest" | "oldest")}><option value="newest">Newest First</option><option value="oldest">Oldest First</option></select>
        </label>
        <span className="total-box">{msgs.length} Total Emails</span>
      </div>
      {view.length === 0 ? (
        <div className="empty"><div className="empty-icon">Mail</div><strong>Your inbox is empty</strong><p>Waiting for incoming emails (10-20 Second)</p></div>
      ) : view.map((m) => <MessageRow key={m.id} msg={m} onOpen={() => void markRead(m.id)} />)}
    </div>
  );
}
