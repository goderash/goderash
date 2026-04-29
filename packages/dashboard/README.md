# @goderash/dashboard

Next.js 14 admin UI for the Goderash control plane. All data fetching happens
in server components; the API key never reaches the browser.

## Run

```bash
cd packages/dashboard
pnpm install
GODERASH_ENDPOINT=http://localhost:8000 \
GODERASH_API_KEY=gdr_... \
GODERASH_TENANT=demo \
  pnpm dev
```

Then open <http://localhost:3000>.

## Pages

| Path | Source | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Overview: chain integrity + counts |
| `/events` | `app/events/page.tsx` | Latest ledger events (paginated) |
| `/verify` | `app/verify/page.tsx` | Re-walks the chain on every load |
| `/packs` | `app/packs/page.tsx` | Available compliance packs |
| `/whatif` | `app/whatif/page.tsx` | Counterfactual replay |
| `/settings` | `app/settings/page.tsx` | Read-only connection info |

## Conventions

- All fetches go through `lib/api.ts` and run server-side only.
- No client-side state in v1 — every page is `dynamic = 'force-dynamic'`.
- Tailwind for styling. The palette is in `tailwind.config.ts`.

## What's missing in v1

- No interactive forms — refining a What-If policy or filtering events
  requires URL params for now.
- No live updates — refresh to re-poll. SSE / WebSocket is the next step.
- Auth is "trust the env" — pair with SSO / VPN / Tailscale before
  exposing publicly.
