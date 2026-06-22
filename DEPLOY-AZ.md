# Deploy A → Z (TempGmail)

Token **chi dat tren may ban**, khong gui vao chat/AI.

## Buoc 0: Token Cloudflare

Dashboard → My Profile → API Tokens → Create Token:

- Template **Edit Cloudflare Workers** + them quyen **D1 Edit**, **Workers R2 Storage**, **Workers KV Storage**, **Account Settings Read**

PowerShell:

```powershell
cd D:\codex\tempgmail
$env:CLOUDFLARE_API_TOKEN = "PASTE_TOKEN_TAI_DAY"
```

Hoac thay bang `npx wrangler login` (bo bien token).

## Buoc 1: Bootstrap (tu dong)

```powershell
npm run cloudflare:bootstrap
```

Script se:

1. `npm install` (neu chua co)
2. Tao D1 `tempmail-db`, R2 `tempmail-attachments`, KV `tempmail-rate-limit` (hoac dung lai neu da co)
3. Ghi `database_id` + KV `id` vao `apps/api/wrangler.toml` va `apps/email-worker/wrangler.toml`
4. Chay tracked D1 migrations trong `migrations/`
5. `wrangler deploy` API roi email-worker
6. Hoi tung **secret** (Enter = bo qua)

## Buoc 2: Secrets can co cho MVP

| Secret | Ghi chu |
|--------|---------|
| `TURNSTILE_SECRET` | Cloudflare Turnstile |
| `BETTER_AUTH_SECRET` | Chuoi random dai |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth + Gmail poll |
| `GMAIL_BACKENDS_JSON` | JSON mang account Gmail backend |
| `OPERATOR_GMAIL` | Email gui forward |
| `STRIPE_*` | Tuy chon premium |
| `DEFAULT_DOMAIN` | `stockai.store` |

## Buoc 3: Email Routing (bat buoc cho domain mail)

Zone `stockai.store` tren Cloudflare:

1. **Email** → Routing → Enable
2. Catch-all → Send to **Worker** `tempmail-email`
3. MX/records theo huong dan CF

## Buoc 4: Web (Pages hoac static)

```powershell
cd apps/web
$env:VITE_API_URL = "https://tempmail-api.<account>.workers.dev"
$env:VITE_TURNSTILE_SITE_KEY = "..."
npm run build
```

Upload `dist/` len **Cloudflare Pages** hoac host static.

## Buoc 5: Stripe webhook (neu dung)

URL: `https://<api-worker>/api/stripe/webhook`  
Secret → `STRIPE_WEBHOOK_SECRET`

## Kiem tra

- `GET https://<api>/api/health` → `{"ok":true}`
- Tao inbox tren web → nhan mail test vao domain

## Loi thuong gap

- **D1 local id**: script da thay `local-tempmail-db` bang UUID that
- **DO**: deploy API truoc email-worker (da lam trong script)
- **403 captcha**: thieu `TURNSTILE_SECRET` hoac site key sai tren web
