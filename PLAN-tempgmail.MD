# Plan coding — TempMail Web (clone tempmailg.com)

## Goal

Xây dựng web TempMail clone [tempmailg.com](http://tempmailg.com) với **đầy đủ tính năng trong ảnh**, chạy trên **Cloudflare** (serverless, low-ops), gồm **2 chế độ song song**:

1. **Custom Domain Inbox** — nhận mail trên domain riêng (vd `oegmail.store`) qua Cloudflare Email Routing. Bền, hợp lệ, full control.
2. **Gmail Alias Inbox** — cấp địa chỉ `@gmail.com` thật bằng kỹ thuật alias (`+tag` + dot-trick), đọc mail từ (các) Gmail backend do bên vận hành sở hữu qua Gmail API. Qua mặt được site chặn domain disposable.

Tính năng UI phải có: ô địa chỉ + Copy, **Refresh, Delete, QR Code, History, Change, Email Forward (NEW), Add Custom Domain, Gmail Generator**, inbox realtime (Filter/Sort/Total/Live/Encrypted), Tools menu, i18n (EN), Sign up/Login, Premium.

## Context

### Hai mô hình nhận mail — so sánh

| Tiêu chí | Custom Domain Inbox | Gmail Alias Inbox |
| --- | --- | --- |
| Địa chỉ | [xxx@oegmail.store](mailto:xxx@oegmail.store) | [o.ff.er.mom.569+tag@gmail.com](mailto:o.ff.er.mom.569+tag@gmail.com) (thật) |
| Nhận mail | Cloudflare Email Routing → Email Worker | Gmail API (poll) đọc Gmail backend của bạn |
| Cần bạn sở hữu | Domain trong Cloudflare | Pool tài khoản Gmail thật + OAuth |
| Qua mặt chặn disposable | Không (domain lạ) | Có (là @[gmail.com](http://gmail.com)) |
| Tính hợp lệ / độ bền | Cao, đúng chuẩn | Rủi ro vi phạm ToS Google, dễ bị khóa |
| Demux user | Theo địa chỉ đích đầy đủ | Theo +tag (dot bị Gmail bỏ qua) |

### Cơ chế Gmail Alias Inbox (điểm dễ hiểu nhầm)

- `offermom569@gmail.com` = Gmail **do bên vận hành tạo & sở hữu**, KHÔNG phải Gmail của người dùng cuối.
- `o.ff.er.mom.569` = dot-trick cho "trông thật"; Gmail bỏ hết dấu chấm → vẫn về `offermom569`.
- `+9ze1iqwa09` = **khóa định danh duy nhất** cho từng user → dùng để tách mail về đúng inbox.
- 1 Gmail backend đẻ được **vô hạn** alias (`+tag` không giới hạn) → vài account nuôi cả nghìn user.
- Người dùng cuối KHÔNG đăng nhập Gmail, chỉ nhận alias và đọc trên web của bạn.

### Sơ đồ luồng

```mermaid
flowchart LR
	S["Người gửi"] -->|@oegmail.store| ER["CF Email Routing"]
	ER --> EW["Email Worker"]
	S -->|+tag@gmail.com| G["Gmail backend (bạn sở hữu)"]
	DO_POLL["MailboxDO alarm ~15s"] -->|Gmail API messages.list| G
	EW --> STORE["D1 + R2 + MailboxDO"]
	DO_POLL --> STORE
	STORE -->|client poll 10-20s| UI["Web inbox"]
	STORE -->|nếu bật Forward| FWD["Gmail send / relay"]
```

### Stack

- **Frontend**: React + Vite + Tailwind + shadcn/ui trên **Cloudflare Pages**.
- **API**: **Hono** trên Cloudflare Workers.
- **Email ingest**: Email Worker (nhánh domain) + MailboxDO poll Gmail API (nhánh Gmail).
- **State**: **Durable Objects** (inbox ephemeral + TTL alarm + poll loop), **D1** (bền), **R2** (attachments), **KV** (rate-limit/config).
- **Bảo vệ**: Turnstile + rate limiting. **Auth/Premium**: Better Auth + Stripe.
- **Realtime**: client **poll 10–20s** (theo tempmailg) cho cả 2 nhánh.

## Tasks

### Nhóm chung

- **T1 — Setup hạ tầng**: tài khoản Cloudflare; add domain `oegmail.store` (zone); bật Email Routing catch-all; tạo Google Cloud project + OAuth client cho Gmail API; tạo pool Gmail backend + OAuth lấy refresh_token.
- **T2 — Monorepo**: `apps/web`, `apps/api`, `apps/email-worker`, `packages/shared`; cấu hình `wrangler.toml`, bindings D1/R2/KV/DO.
- **T3 — D1 schema + drizzle migrations**: `mailboxes`, `gmail_mailboxes`, `domains`, `users`, `sessions`.
- **T4 — MailboxDO**: storage messages + TTL `alarm()` + poll loop (nhánh Gmail) + broadcast.

### Nhánh Custom Domain (D-series)

- **D1 — Email Worker ingest**: parse `postal-mime` → attachments lên R2 → đẩy DO → forward.
- **D2 — Tạo địa chỉ**: random local-part @ domain hệ thống; ghi D1; set TTL.
- **D3 — Add Custom Domain**: user thêm domain riêng → verify TXT; lưu ý Email Routing chỉ chạy với zone trong Cloudflare.

### Nhánh Gmail Alias (G-series)

- **G1 — OAuth backend**: lưu refresh_token; hàm `getAccessToken`.
- **G2 — Cấp alias**: random `+tag` + dotify; map `alias_key = account#tag`.
- **G3 — Poll loop**: MailboxDO alarm ~15s gọi `messages.list`, lọc theo `internalDate`, parse, demux theo `+tag`, đổ vào mailbox; ngừng khi hết user active (tiết kiệm quota).
- **G4 — Gmail Generator UI**: hiển thị alias + Copy.

### Tính năng UI

- **U1 — Inbox**: poll 10–20s, Filter (All/Unread), Sort (Newest/Oldest), Total Emails, Live, Encrypted, empty state.
- **U2 — Nút**: Refresh, Delete, QR Code (lib qrcode), History (alias đã cấp), Change (rotate).
- **U3 — Email Forward (NEW)**: dialog nhập địa chỉ đích → lưu `forward_to`; backend forward khi có mail.
- **U4 — Render mail an toàn**: iframe `sandbox` chống XSS; tải attachment từ R2.
- **U5 — i18n / Tools menu / Telegram / Premium / Sign up-Login**.

### Phụ trợ

- **P1 — Turnstile + rate limit**. **P2 — Auth + Stripe (Premium)**. **P3 — Abuse & cleanup (Cron dọn hết hạn)**. **P4 — Tests (vitest + playwright)**. **P5 — Deploy & docs**.

## Tool Plan

Mô tả từng function kèm demo code.

### 1. Email Worker — ingest nhánh domain

```tsx
import PostalMime from "postal-mime";

export interface Env {
	DB: D1Database;
	ATTACHMENTS: R2Bucket;
	MAILBOX: DurableObjectNamespace;
}

export default {
	async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
		const to = message.to.toLowerCase();
		const row = await env.DB.prepare(
			"SELECT forward_to, expires_at FROM mailboxes WHERE address = ?",
		).bind(to).first<{ forward_to: string | null; expires_at: number }>();
		if (!row || row.expires_at < Date.now()) {
			message.setReject("550 5.1.1 Mailbox unavailable");
			return;
		}
		const raw = await new Response(message.raw).arrayBuffer();
		const email = await new PostalMime().parse(raw);
		const attachments = [];
		for (const att of email.attachments ?? []) {
			const id = crypto.randomUUID();
			const key = `att/${to}/${id}`;
			await env.ATTACHMENTS.put(key, att.content, { httpMetadata: { contentType: att.mimeType } });
			attachments.push({ id, key, name: att.filename, type: att.mimeType });
		}
		const msg = {
			id: crypto.randomUUID(), from: email.from?.address ?? "",
			subject: email.subject ?? "(no subject)", text: email.text ?? "",
			html: email.html ?? "", attachments, receivedAt: Date.now(), read: false,
		};
		const stub = env.MAILBOX.get(env.MAILBOX.idFromName(to));
		ctx.waitUntil(stub.fetch("https://do/add", { method: "POST", body: JSON.stringify(msg) }));
		if (row.forward_to) await message.forward(row.forward_to);
	},
};
```

### 2. MailboxDO — inbox ephemeral + TTL + poll Gmail

```tsx
export class MailboxDO implements DurableObject {
	constructor(private state: DurableObjectState, private env: Env) {}

	async fetch(req: Request): Promise<Response> {
		const url = new URL(req.url);
		if (url.pathname === "/add" && req.method === "POST") {
			const msg = await req.json();
			const msgs = (await this.state.storage.get("msgs")) ?? [];
			msgs.unshift(msg);
			await this.state.storage.put("msgs", msgs.slice(0, 100));
			return new Response("ok");
		}
		if (url.pathname === "/list") {
			return Response.json((await this.state.storage.get("msgs")) ?? []);
		}
		if (url.pathname === "/expire" && req.method === "POST") {
			const { at } = await req.json();
			await this.state.storage.setAlarm(at);
			return new Response("ok");
		}
		if (url.pathname === "/poll-start") {
			await this.state.storage.put("active", true);
			await this.state.storage.setAlarm(Date.now() + 15000); // poll ~15s
			return new Response("ok");
		}
		return new Response("not found", { status: 404 });
	}

	async alarm() {
		const active = await this.state.storage.get("active");
		if (active) {
			await pollGmailForThisMailbox(this.env, this.state); // nhánh Gmail
			await this.state.storage.setAlarm(Date.now() + 15000); // lặp lại
		} else {
			await this.state.storage.deleteAll(); // TTL hết hạn
		}
	}
}
```

### 3. API Worker (Hono)

```tsx
import { Hono } from "hono";
import { cors } from "hono/cors";
const app = new Hono<{ Bindings: Env }>();
app.use("/api/*", cors());

// Tạo địa chỉ domain
app.post("/api/mailbox", async (c) => {
	const { turnstileToken } = await c.req.json();
	const ip = c.req.header("CF-Connecting-IP") ?? "";
	if (!(await verifyTurnstile(turnstileToken, ip, c.env))) return c.json({ error: "captcha" }, 403);
	if (!(await allowRate(c.env, ip))) return c.json({ error: "rate" }, 429);
	const address = `${randomLocal()}@oegmail.store`;
	const expiresAt = Date.now() + 3600_000;
	await c.env.DB.prepare(
		"INSERT INTO mailboxes (address, expires_at, created_at) VALUES (?,?,?)",
	).bind(address, expiresAt, Date.now()).run();
	const stub = c.env.MAILBOX.get(c.env.MAILBOX.idFromName(address));
	await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
	return c.json({ address, expiresAt });
});

app.get("/api/mailbox/:addr/messages", async (c) => {
	const stub = c.env.MAILBOX.get(c.env.MAILBOX.idFromName(c.req.param("addr").toLowerCase()));
	return stub.fetch("https://do/list");
});

app.get("/api/attachments/:key{.+}", async (c) => {
	const obj = await c.env.ATTACHMENTS.get(c.req.param("key"));
	if (!obj) return c.notFound();
	return new Response(obj.body, { headers: { "content-type": obj.httpMetadata?.contentType ?? "application/octet-stream" } });
});

export default app;
export { MailboxDO } from "./mailbox-do";
```

Helper bảo vệ:

```tsx
async function verifyTurnstile(token: string, ip: string, env: Env) {
	const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
		method: "POST", headers: { "content-type": "application/json" },
		body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip }),
	});
	return (await res.json()).success;
}
async function allowRate(env: Env, ip: string) {
	const key = `rl:${ip}:${Math.floor(Date.now() / 60000)}`;
	const n = Number((await env.RATE_LIMIT.get(key)) ?? "0");
	if (n >= 10) return false;
	await env.RATE_LIMIT.put(key, String(n + 1), { expirationTtl: 120 });
	return true;
}
const randomLocal = () => "u" + crypto.randomUUID().replace(/-/g, "").slice(0, 10);
```

### 4. Nhánh Gmail — OAuth, cấp alias, poll, demux

```tsx
async function getAccessToken(env: Env, refreshToken: string): Promise<string> {
	const res = await fetch("https://oauth2.googleapis.com/token", {
		method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams({
			client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET,
			refresh_token: refreshToken, grant_type: "refresh_token",
		}),
	});
	return (await res.json()).access_token;
}

// Cấp alias Gmail
app.post("/api/gmail-mailbox", async (c) => {
	const account = pickBackingGmail(c.env);          // offermom569@gmail.com (bạn sở hữu)
	const tag = crypto.randomUUID().replace(/-/g, "").slice(0, 10);
	const display = dotify(account.local) + "+" + tag + "@gmail.com";
	const aliasKey = account.email + "#" + tag;
	await c.env.DB.prepare(
		"INSERT INTO gmail_mailboxes (alias_key, display_address, backing_account, plus_tag, expires_at, created_at) VALUES (?,?,?,?,?,?)",
	).bind(aliasKey, display, account.email, tag, Date.now() + 3600_000, Date.now()).run();
	const stub = c.env.MAILBOX.get(c.env.MAILBOX.idFromName(aliasKey));
	await stub.fetch("https://do/poll-start");        // bật poll loop ~15s
	return c.json({ address: display, aliasKey, expiresAt: Date.now() + 3600_000 });
});

function dotify(local: string) {
	return local.split("").map((ch, i) => (i > 0 && Math.random() < 0.3 ? "." + ch : ch)).join("");
}
```

```tsx
// Poll Gmail API + demux theo +tag (gọi trong MailboxDO.alarm)
async function pollGmailForThisMailbox(env: Env, state: DurableObjectState) {
	const account = await state.storage.get<string>("account");
	const tag = await state.storage.get<string>("tag");
	const token = await getAccessToken(env, await lookupRefreshToken(env, account));
	const list = await fetch(
		"https://gmail.googleapis.com/gmail/v1/users/me/messages?q=" +
		encodeURIComponent(`to:(${account.split("@")[0]}+${tag}@gmail.com) newer_than:1d`),
		{ headers: { authorization: `Bearer ${token}` } },
	).then((r) => r.json());
	for (const m of list.messages ?? []) {
		const msg = await fetchMessage(token, m.id);
		if (extractPlusTag(msg.to) !== tag) continue;   // chắc chắn đúng tag
		const msgs = (await state.storage.get("msgs")) ?? [];
		if (msgs.find((x) => x.id === msg.id)) continue; // tránh trùng
		msgs.unshift(msg);
		await state.storage.put("msgs", msgs.slice(0, 100));
		await maybeForward(env, token, account + "#" + tag, msg);
	}
}

function extractPlusTag(to = "") {
	const m = to.match(/\+([a-z0-9]+)@gmail\.com/i);
	return m ? m[1].toLowerCase() : null;
}

async function fetchMessage(token: string, id: string) {
	const raw = await fetch(
		"https://gmail.googleapis.com/gmail/v1/users/me/messages/" + id + "?format=full",
		{ headers: { authorization: `Bearer ${token}` } },
	).then((r) => r.json());
	const H: Record<string, string> = {};
	for (const h of raw.payload.headers) H[h.name.toLowerCase()] = h.value;
	return {
		id, from: H["from"] ?? "", to: H["to"] ?? H["delivered-to"] ?? "",
		subject: H["subject"] ?? "(no subject)",
		text: decodeBody(raw.payload, "text/plain"), html: decodeBody(raw.payload, "text/html"),
		receivedAt: Number(raw.internalDate), read: false,
	};
}
```

> Demux chỉ dựa vào `+tag` (Gmail bỏ qua dấu chấm nên đừng dựa vào dot). `+tag` phải đủ dài để không trùng.
> 

### 5. Email Forward (NEW)

```tsx
async function maybeForward(env: Env, token: string, aliasKey: string, msg: any) {
	const row = await env.DB.prepare(
		"SELECT forward_to FROM gmail_mailboxes WHERE alias_key = ?",
	).bind(aliasKey).first<{ forward_to: string | null }>();
	if (!row?.forward_to) return;
	const rawMime = [
		`From: TempMail <${env.OPERATOR_GMAIL}>`,
		`To: ${row.forward_to}`,
		`Reply-To: ${msg.from}`,
		`Subject: [Fwd] ${msg.subject}`,
		`Content-Type: text/html; charset=UTF-8`, ``, msg.html || msg.text,
	].join("\r\n");
	await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
		method: "POST",
		headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
		body: JSON.stringify({ raw: b64url(rawMime) }),
	});
}

app.post("/api/gmail-mailbox/:aliasKey/forward", async (c) => {
	const { forwardTo } = await c.req.json();
	await c.env.DB.prepare("UPDATE gmail_mailboxes SET forward_to = ? WHERE alias_key = ?")
		.bind(forwardTo, c.req.param("aliasKey")).run();
	return c.json({ ok: true });
});
```

### 6. Inbox UI (poll 10–20s, Filter/Sort/Live/Total)

```tsx
function Inbox({ aliasKey }: { aliasKey: string }) {
	const [msgs, setMsgs] = useState<Msg[]>([]);
	const [filter, setFilter] = useState<"all" | "unread">("all");
	const [sort, setSort] = useState<"newest" | "oldest">("newest");
	const [live, setLive] = useState(false);

	useEffect(() => {
		let alive = true;
		const poll = async () => {
			const data = await fetch(`/api/mailbox/${aliasKey}/messages`).then((r) => r.json());
			if (alive) { setMsgs(data); setLive(true); }
		};
		poll();
		const id = setInterval(poll, 15000); // Waiting for incoming emails (10-20 Second)
		return () => { alive = false; clearInterval(id); };
	}, [aliasKey]);

	const view = useMemo(() => {
		const f = filter === "unread" ? msgs.filter((m) => !m.read) : msgs;
		return [...f].sort((a, b) => sort === "newest" ? b.receivedAt - a.receivedAt : a.receivedAt - b.receivedAt);
	}, [msgs, filter, sort]);

	return (
		<div>
			<header>
				<h2>Inbox <span>{view.filter((m) => !m.read).length} New</span></h2>
				<span>{live ? "🟢 Live" : "…"}</span><span>🔒 Encrypted</span>
			</header>
			<div>
				<select value={filter} onChange={(e) => setFilter(e.target.value as any)}>
					<option value="all">All Emails</option><option value="unread">Unread</option>
				</select>
				<select value={sort} onChange={(e) => setSort(e.target.value as any)}>
					<option value="newest">Newest First</option><option value="oldest">Oldest First</option>
				</select>
				<span>{msgs.length} Total Emails</span>
			</div>
			{view.length === 0
				? <Empty title="Your inbox is empty" subtitle="Waiting for incoming emails (10-20 Second)" />
				: view.map((m) => <MessageRow key={m.id} msg={m} />)}
		</div>
	);
}
```

Render mail an toàn:

```tsx
function MessageBody({ html }: { html: string }) {
	return <iframe sandbox="" srcDoc={html} title="email-body" className="w-full h-[60vh]" />;
}
```

### 7. Map các nút trong ảnh

| Nút | Hành động |
| --- | --- |
| Copy | copy display_address vào clipboard |
| Refresh | gọi poll() thủ công |
| Delete | DELETE mailbox → xoá D1 + DO deleteAll |
| QR Code | encode địa chỉ bằng lib qrcode |
| History | GET /api/history → alias đã cấp cho session |
| Change | cấp tag/địa chỉ mới, ẩn cái cũ |
| Email Forward (NEW) | dialog nhập đích → POST .../forward |
| Add Custom Domain | thêm domain riêng + verify TXT |
| Gmail Generator | cấp alias @[gmail.com](http://gmail.com)  • Copy |

### 8. wrangler.toml (email-worker)

```toml
name = "tempmail-email"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "tempmail-db"
database_id = "<id>"

[[r2_buckets]]
binding = "ATTACHMENTS"
bucket_name = "tempmail-attachments"

[[durable_objects.bindings]]
name = "MAILBOX"
class_name = "MailboxDO"

[[migrations]]
tag = "v1"
new_classes = ["MailboxDO"]
```

Lệnh hay dùng:

```bash
wrangler d1 create tempmail-db
wrangler r2 bucket create tempmail-attachments
wrangler kv namespace create RATE_LIMIT
wrangler deploy            # workers (api + email)
wrangler pages deploy dist # frontend
wrangler tail              # xem log realtime
```

## Acceptance Criteria

- [ ]  Tạo địa chỉ tạm cả 2 chế độ: `@oegmail.store` và `@gmail.com` (+tag).
- [ ]  Gửi mail tới địa chỉ → hiện trong inbox web trong ≤ 20s (poll 10–20s).
- [ ]  Inbox có Filter (All/Unread), Sort (Newest/Oldest), Total Emails, Live, Encrypted, empty state đúng như ảnh.
- [ ]  Các nút hoạt động: Copy, Refresh, Delete, QR Code, History, Change.
- [ ]  Email Forward: bật/tắt + forward mail mới tới địa chỉ đích, Reply-To = người gửi gốc.
- [ ]  Add Custom Domain: verify TXT thành công thì nhận được mail trên domain đó.
- [ ]  Attachment tải được từ R2; mail HTML render trong iframe sandbox (không chạy script).
- [ ]  Turnstile + rate limit chặn tạo hàng loạt.
- [ ]  TTL: địa chỉ hết hạn thì DO tự xoá message + ngừng poll.
- [ ]  i18n EN, Sign up/Login, Premium (Stripe) hoạt động cơ bản.

## Risks

- **Gmail backend vi phạm ToS Google**: nuôi temp-mail công cộng bằng Gmail cá nhân dễ bị **khóa account** + dính quota Gmail API. Rủi ro lớn nhất của nhánh Gmail. Mitigation: pool account riêng biệt, không dùng account quan trọng; sẵn sàng fallback sang nhánh domain.
- **Quota Gmail API** (1.2M units/ngày/project, 250 units/user/giây): poll 15s × nhiều mailbox tốn quota → giới hạn số mailbox active đồng thời / nhiều project.
- **Poll trễ tối đa ~15s** (đánh đổi đã chọn so với push realtime).
- **Durable Objects cần Workers Paid plan**.
- **Email Routing chỉ chạy với zone trong Cloudflare** → Add Custom Domain yêu cầu user add domain vào Cloudflare (hoặc chỉ cho subdomain của bạn).
- **`message.forward()` (nhánh domain) cần địa chỉ đích đã verify** trong Email Routing; forward nhánh Gmail gửi từ account của bạn → dễ vào spam nếu volume cao (cân nhắc relay + SPF/DKIM).
- **Bảo mật render HTML**: bắt buộc iframe sandbox; lọc tracking pixel nếu cần.
- **Lạm dụng**: temp-mail hay bị dùng cho abuse → cần rate limit, chặn domain nhạy cảm, log tối thiểu.

## Phụ lục — nhánh self-host (tham khảo)

Nếu sau này muốn **treo 24/7 trên VPS** thay vì Cloudflare: dùng **Go** (single binary, RAM thấp) với `emersion/go-smtp` + `go-message`, store in-memory + TTL, WebSocket realtime, systemd. Tối ưu nhất cho VPS tài nguyên thấp nhưng phải tự quản hạ tầng + TLS + uptime.