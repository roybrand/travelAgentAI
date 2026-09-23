# Production checklist

Exactly what to do, in order, to take Wayfinder AI from "running on my laptop" to "running for
real users." Written for you, the founder — not for a general audience. Check items off as you go.

Deeper detail on any of these already exists elsewhere in this folder; this file is the flat to-do
list that pulls it all together. Related: [06 · Go live and partnerships](06-go-live-and-partnerships.md)
(the business/partner side of going live), [05 · Live data and AI](05-live-data-and-ai.md)
(every setting explained).

## If you do nothing else, do these five

1. **Commit and push what's built.** Nothing since commit `757f3c4` is committed — that's the Day
   plan, all 100 demo people, 124 demo businesses, the Radar/Alerts system, trust & safety
   hardening, Featured payments, real push, self-hosted analytics, and auth hardening. Ask me to
   commit it, or run `git add -A && git commit` yourself.
2. **Rotate every secret that was ever pasted into a chat, a screenshot or a log** — most
   importantly `OPENAI_API_KEY`. Generate a fresh key at platform.openai.com, put it only in
   `backend/.env`, and revoke the old one.
3. **Get hosting and a domain** (below). Nothing else here matters until the app is reachable at a
   real HTTPS address — several features (real push, an installable app) flatly require HTTPS.
4. **Write a Privacy Policy and Terms of Service and show them at sign-up.** You are already
   collecting photos, messages, birth years and (rounded) locations for Wayfinder People. This is
   not optional once a real stranger's data is involved.
5. **Set `ADMIN_TOKEN` to a fresh long random value** you haven't used anywhere else, and keep it
   only in your production `.env`. It's the only thing standing between the internet and your
   moderation queue.

---

## 1. Secrets and configuration

Copy `backend/.env.example` to `backend/.env` on the production server and fill in:

| Variable | Required? | Get it from | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | Recommended | platform.openai.com | Powers plain-English trip requests, AI summaries, photo moderation. App works without it (keyword fallback), but noticeably worse |
| `AMADEUS_CLIENT_ID` / `_SECRET` | Optional | developers.amadeus.com (free) | Real flight/hotel prices instead of estimates. Switch `AMADEUS_BASE_URL` from the test URL to the production one once Amadeus approves you |
| `TICKETMASTER_API_KEY` | Optional | developer.ticketmaster.com (free) | Live events |
| `TRAVELPAYOUTS_TOKEN` | Optional | travelpayouts.com (free) | Recent real fares |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Needed to actually collect Featured-placement fees | stripe.com | Start in **test mode**, confirm a full paid flow works, then switch to your live key. Create the webhook endpoint pointing at `https://<your-domain>/api/payments/stripe/webhook` in the Stripe dashboard to get the webhook secret |
| `VAPID_PUBLIC_KEY` / `_PRIVATE_KEY` / `_SUBJECT` | Needed for real push | `python scripts/generate_vapid_keys.py` | Generate **fresh ones for production** — regenerate rather than reusing the pair from development, since those were visible in this session's history. Set `VAPID_SUBJECT` to a real contact email |
| `ADMIN_TOKEN` | Required | any long random string (`openssl rand -hex 32`) | Without it, `/admin` refuses to work at all — safe default, but you need it set to use moderation |
| `WAYFINDER_DB` | Optional | — | Leave unset unless you move off SQLite (see §3) |
| `WAYFINDER_OFFLINE` | Must be unset or `0` | — | Only `1` in the test suite; never on a real server |

Never commit `backend/.env`. It already sits in `.gitignore`.

## 2. Hosting and deployment

Nothing here picks a provider for you — pick whichever you're comfortable operating. In order of
setup effort for a small FastAPI + SQLite app:

- [ ] **Choose a host.** A single small VM (Hetzner, DigitalOcean, a Lightsail instance) or a
  PaaS (Railway, Render, Fly.io) both work — this app is one process, no queue, no cache. A PaaS
  is less to operate; a VM is cheaper at this scale and gives you a filesystem for the SQLite file.
- [ ] **Write a Dockerfile** (there isn't one yet) or a systemd service that runs:
  ```
  cd frontend && npm ci && npm run build      # produces frontend/dist, git-ignored, built at deploy time
  cd backend && pip install -r requirements.txt
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
  The backend serves the built frontend itself — one process, one port, no separate static host needed.
- [ ] **Put it behind HTTPS.** A reverse proxy (Caddy or nginx with Let's Encrypt, or your PaaS's
  built-in TLS) in front of port 8000. Real push notifications and the installable-app manifest
  both require HTTPS (or `localhost`, which production isn't).
- [ ] **Buy and point a domain** at the host. Update anything that assumes `localhost:8000`.
- [ ] **Persistent disk for `backend/data/`** (the SQLite file, partner/People photos). If your
  host's filesystem is ephemeral (most PaaS free tiers), attach a persistent volume or you will
  lose every account and deal on the next deploy.
- [ ] **A CI step (or a pre-deploy script) that runs `npm run build` and `pytest`** before every
  deploy, so a broken build or a failing test never reaches production.

## 3. Data and backups

- [ ] **Back up `backend/data/partners.db`** on a schedule (a daily cron copying it to S3/Backblaze
  is enough at this scale). Right now a lost disk means a lost database — there is no backup at all.
- [ ] **Plan the Postgres move before you need it**, not during an outage. SQLite comfortably
  handles a single-writer prototype; move once you have real concurrent write load (many partners
  and travelers acting at once). The schema in `backend/app/partners/db.py` is plain SQL, so this
  is a driver change, not a redesign — but it is real work, budget a day for it.
- [ ] **Rate limits currently live in memory** (`app/partners/security.py`), so they reset on every
  restart and don't share state across multiple server instances. Fine for one process; revisit if
  you ever run more than one.

## 4. Legal and trust & safety

- [ ] **Privacy Policy and Terms of Service**, linked from sign-up on both Wayfinder People and the
  partner portal. You are a data controller under GDPR/CCPA the moment a real photo or message is
  stored — this needs a lawyer's eyes, not just a template.
- [ ] **Age verification is currently self-declared** (a birth year, a checkbox). Depending on your
  target markets, a legal review of whether that's sufficient for a stranger-meetup feature is
  worth doing before wide launch — see [09 · People and safety §6](09-people-and-safety.md).
- [ ] **Email verification and password reset don't exist yet** — both need an email service
  (Postmark, SendGrid, AWS SES are common free-tier options). "Change my password while signed in"
  is built; "I forgot my password" is not.
- [ ] **Decide your moderation capacity.** Photos and reports queue at `/admin` either way; with an
  `OPENAI_API_KEY` set, obviously-bad photos are auto-rejected, but someone still has to look at
  the queue regularly, especially early on.
- [ ] **Local emergency numbers are not shown anywhere in the app.** Worth adding before real
  in-person meetups happen at scale.

## 5. Payments (only if you're turning on Featured placements)

- [ ] Create your Stripe account, verify it (Stripe will ask for real business/bank details before
  paying out to you).
- [ ] Start in Stripe **test mode**: set `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` to the test
  values, register a test partner account, click "Feature this deal," and pay with Stripe's test
  card `4242 4242 4242 4242` end to end. Confirm the deal actually shows "Featured" afterward.
- [ ] Switch to your **live** Stripe keys only once that works, and re-test with a real (small)
  charge.
- [ ] Decide your refund policy for a featured placement and be ready to issue one manually from
  the Stripe dashboard — there's no in-app refund flow yet.
- [ ] If you ever want to pay a *partner* directly through Wayfinder (rather than just collecting
  a placement fee from them), that's Stripe Connect — a materially bigger project (partner
  onboarding, KYC, payouts). Not needed for what's built today.

## 6. Analytics and monitoring

- [ ] The built-in `/admin` analytics dashboard works with zero setup — nothing to do here to get
  basic signup/engagement numbers.
- [ ] **No error tracking or uptime monitoring exists.** Add one (Sentry's free tier for errors, a
  free uptime pinger like UptimeRobot for availability) before you have real users depending on
  the app being up.
- [ ] **No structured application logs beyond the two markdown activity logs** (`backend/logs/`).
  Fine at this scale; if you outgrow it, ship logs somewhere queryable (even just journald + `grep`
  on the VM is enough for a while).

## 7. Final pre-launch pass

- [ ] Run the full test suite one more time on the production branch: `cd backend && python -m
  pytest` — should be 300 passed.
- [ ] Run `python scripts/sync_docs.py` (from `backend/`) and confirm `git status` shows no
  changes (docs match code).
- [ ] Load the production URL on an actual phone, not just a laptop browser — check the install
  prompt, push permission prompt, and bottom nav all work.
- [ ] Delete or clearly label any leftover test accounts you created while trying things out (this
  session's smoke tests were all cleaned up, but check your own).
- [ ] Re-read [09 · People and safety §6](09-people-and-safety.md) ("What is not built") one more
  time immediately before letting real strangers message each other.
