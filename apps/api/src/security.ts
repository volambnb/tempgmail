import type { Env } from "./env";

export async function verifyTurnstile(token: string | undefined, ip: string, env: Env): Promise<boolean> {
  if (!env.TURNSTILE_SECRET) return true;
  if (!token) return false;
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip }),
  });
  const data = (await res.json()) as { success?: boolean };
  return Boolean(data.success);
}

export async function allowRate(env: Env, ip: string, limit = 10): Promise<boolean> {
  const key = `rl:${ip}:${Math.floor(Date.now() / 60000)}`;
  const n = Number((await env.RATE_LIMIT.get(key)) ?? "0");
  if (n >= limit) return false;
  await env.RATE_LIMIT.put(key, String(n + 1), { expirationTtl: 120 });
  return true;
}

const FIRST_NAMES = [
  "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
  "thomas", "charles", "daniel", "matthew", "anthony", "mark", "donald", "steven",
  "paul", "andrew", "joshua", "kenneth", "kevin", "brian", "george", "edward",
  "ronald", "timothy", "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas",
  "eric", "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
  "samuel", "gregory", "alexander", "patrick", "frank", "raymond", "jack", "dennis",
  "emma", "olivia", "ava", "sophia", "isabella", "mia", "charlotte", "amelia",
  "harper", "evelyn", "abigail", "emily", "elizabeth", "sofia", "avery", "ella",
  "scarlett", "grace", "chloe", "victoria", "riley", "aria", "lily", "nora",
  "zoey", "hannah", "lillian", "addison", "aubrey", "ellie", "stella", "natalie",
];

const LAST_NAMES = [
  "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
  "rodriguez", "martinez", "hernandez", "lopez", "gonzalez", "wilson", "anderson",
  "thomas", "taylor", "moore", "jackson", "martin", "lee", "perez", "thompson",
  "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson", "walker",
  "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill",
  "flores", "green", "adams", "nelson", "baker", "hall", "rivera", "campbell",
  "mitchell", "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz",
  "parker", "cruz", "edwards", "collins", "reyes", "stewart", "morris", "murphy",
];

function pick(items: string[]): string {
  return items[crypto.getRandomValues(new Uint32Array(1))[0] % items.length];
}

function randomNumber(): number {
  return 10 + (crypto.getRandomValues(new Uint32Array(1))[0] % 90);
}

export function randomLocal(): string {
  return `${pick(FIRST_NAMES)}.${pick(LAST_NAMES)}${randomNumber()}`;
}

export function randomReadableTag(): string {
  return randomLocal().replace(".", "");
}

export function sessionIdFromRequest(req: Request): string {
  const cookie = req.headers.get("Cookie") ?? "";
  const m = cookie.match(/tm_session=([^;]+)/);
  if (m) return m[1];
  return crypto.randomUUID();
}

export const sessionId = sessionIdFromRequest;
