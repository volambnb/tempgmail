from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "apps/api/src/routes.ts"
t = p.read_text(encoding="utf-8")
if "registerAuthRoutes" not in t:
    t = t.replace(
        'import { dotify, pickBackingGmail } from "./gmail";',
        'import { dotify, pickBackingGmail } from "./gmail";\nimport { registerAuthRoutes } from "./auth";\nimport { registerStripeRoutes } from "./stripe";',
    )
    t = t.replace(
        '  app.get("/api/health", (c) => c.json({ ok: true }));',
        '  registerAuthRoutes(app);\n  registerStripeRoutes(app);\n\n  app.get("/api/health", (c) => c.json({ ok: true }));',
    )
    p.write_text(t, encoding="utf-8")
print("routes", len(t))
