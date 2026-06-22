# Gmail backend setup

Use this when you want TempGmail to create many real `@gmail.com` aliases from Gmail accounts you own.

## What happens

One Gmail account can receive many aliases:

- `mygmail@gmail.com`
- `m.y.g.m.a.i.l@gmail.com`
- `mygmail+abc123@gmail.com`
- `m.y.gmail+abc123@gmail.com`

All of those arrive in the original `mygmail@gmail.com` inbox. TempGmail uses the `+abc123` tag to split messages into temporary inboxes.

## Google Cloud one-time setup

1. Open Google Cloud Console.
2. Create a project.
3. Enable **Gmail API**.
4. Configure OAuth consent screen.
5. Create OAuth Client:
   - Application type: **Desktop app**
   - Save `Client ID`
   - Save `Client secret`

Scopes used by this project:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`

`gmail.readonly` reads incoming alias mail. `gmail.send` is only needed for premium forwarding from Gmail aliases.

## Add one Gmail backend

Run this from PowerShell:

```powershell
cd D:\codex\tempgmail
.\scripts\add-gmail-backend.ps1 `
  -ClientId "GOOGLE_CLIENT_ID_HERE" `
  -ClientSecret "GOOGLE_CLIENT_SECRET_HERE" `
  -Email "your-gmail@gmail.com"
```

The script opens Google login. Log in as that Gmail account and allow access.

It saves the backend to:

```text
D:\codex\tempgmail\gmail-backends.json
```

## Add more Gmail accounts

Run the same command again with another Gmail address:

```powershell
.\scripts\add-gmail-backend.ps1 `
  -ClientId "GOOGLE_CLIENT_ID_HERE" `
  -ClientSecret "GOOGLE_CLIENT_SECRET_HERE" `
  -Email "second-gmail@gmail.com"
```

The script appends or replaces that Gmail entry.

## Upload Gmail secrets to Cloudflare

After adding all Gmail accounts:

```powershell
cd D:\codex\tempgmail
.\scripts\push-gmail-secrets.ps1 `
  -GoogleClientId "GOOGLE_CLIENT_ID_HERE" `
  -GoogleClientSecret "GOOGLE_CLIENT_SECRET_HERE"
```

This uploads:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GMAIL_BACKENDS_JSON`

Do not paste refresh tokens into chat.

## After deploy

When the web app calls **Gmail Generator**, the API chooses one backend account and creates an alias like:

```text
m.y.g.m.a.i.l+8f31ca92d001@gmail.com
```

Mail sent there arrives in your backend Gmail inbox, and TempGmail polls Gmail API to show it in the temporary inbox.
