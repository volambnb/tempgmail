# TempGmail

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
4. Enable **Email Routing** catch-all for `stockai.store` (and premium domains) to the email worker.
5. Add secrets: `TURNSTILE_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BETTER_AUTH_SECRET`, optional `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.

## Gmail backends

Use `GMAIL-BACKENDS.md` when adding Gmail accounts for the Gmail Generator.
Short version:

```powershell
.\scripts\add-gmail-backend.ps1 -ClientId "..." -ClientSecret "..." -Email "your-gmail@gmail.com"
.\scripts\push-gmail-secrets.ps1 -GoogleClientId "..." -GoogleClientSecret "..."
```

## Migrations

Apply tracked D1 migrations from `apps/api` with `wrangler d1 migrations apply tempmail-db --remote`.

## Tests

```bash
npm test
npm run build
```
