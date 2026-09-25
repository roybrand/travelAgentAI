# Production checklist

Exactly what to do, in order, to take Wayfinder AI from "running on my laptop" to "running for
real users." Written for you, the founder — not for a general audience. Check items off as you go.

Deeper detail on any of these already exists elsewhere in this folder; this file is the flat to-do
list that pulls it all together. Related: [06 · Go live and partnerships](06-go-live-and-partnerships.md)
(the business/partner side of going live), [05 · Live data and AI](05-live-data-and-ai.md)
(every setting explained). None of this is legal or tax advice: the items marked **lawyer** or
**accountant** need one.

## If you do nothing else, do these eight

1. **Commit anything outstanding and push it to a remote you control.** Check `git status`, commit, then
   make sure the code also lives off this laptop (a private GitHub repo is enough).
2. **Rotate every secret that was ever pasted into a chat, a screenshot or a log** — most
   importantly `OPENAI_API_KEY`. Generate a fresh key at platform.openai.com, put it only in
   `backend/.env`, and revoke the old one.
3. **Set up the business before any money arrives** (§0): a company or sole trader, a business bank
   account, tax registration and an accountant. Affiliate programmes and Stripe will not pay out without them.
4. **Keep travelers' money out of Wayfinder** (§0, §4). Every booking today is a labelled demo. Before
   launch, each part must hand off to a real seller (supplier, affiliate or the business itself), and
   the "Pay now, in the app" option for deals must be switched off until Stripe Connect exists.
5. **Get hosting and a domain** (§2). Nothing else here matters until the app is reachable at a
   real HTTPS address — several features (real push, an installable app) flatly require HTTPS.
6. **Write a Privacy Policy, Terms of Service and Terms for businesses, and show them at sign-up**
   (§5). You already store photos, messages, birth years, rounded locations and reservations.
7. **Replace the free data services that forbid commercial use** (§6), Open-Meteo first: it now
   powers both the season chart and the trip-day forecast.
8. **Set `ADMIN_TOKEN` to a fresh long random value** you haven't used anywhere else, and keep it
   only in your production `.env`. It's the only thing standing between the internet and your
   moderation queue.

---

## 0. Business model and money

**The decision:** Wayfinder does not take travelers' money at this stage. Suppliers and businesses
are paid directly by the traveler; Wayfinder earns commissions and fees for its own service, and
never ranks anything by who pays (a rule the tests enforce).

| Revenue | Who pays you | How it reaches your bank | Status in the app |
|---|---|---|---|
| Pay per guest from local businesses (per **redeemed voucher**) | Partner businesses | Monthly invoice; later auto-charged via Stripe Billing | Reservations and voucher check-in are **built**; fees and invoicing are **not** |
| Affiliate commissions (hotels, activities, flights) | Booking.com, Viator/GetYourGuide, flight partners | Their monthly payout to your bank (some offer PayPal), after the trip | **Not built**: needs your affiliate IDs, then hand-off buttons |
| Featured placements | Partner businesses | Stripe Checkout, paid up front | **Built** (needs live Stripe keys) |
| Wayfinder Plus subscription (later) | Travelers, via Apple/Google | App stores pay you monthly, minus 15–30% | **Not built** |

**Set up once (you):**
- [ ] **Register a business** (company or sole trader, per your country). **Accountant.**
- [ ] **Open a business bank account.** Every payout lands here.
- [ ] **Tax registration** (VAT/sales tax as applicable) and invoice details (legal name, address, tax
  number). **Accountant.**
- [ ] **Create and verify a Stripe account** (§7). It's how businesses pay you, never how travelers pay.

**Affiliate sign-ups (you), once the app has a real domain:**
- [ ] **Hotels:** Booking.com affiliate programme (links with your affiliate ID; they pay monthly after
  the stay). For booking inside the app later: Expedia Rapid API (approval needed, Expedia stays the seller).
- [ ] **Activities:** Viator and/or GetYourGuide partner programmes.
- [ ] **Flights:** a flight affiliate (Travelpayouts is already partly wired for fares) or **Duffel**
  if you want flights sold without IATA accreditation.
- [ ] Add payout bank details and **tax forms** in each partner centre (for example W-8BEN for US
  programmes if you're outside the US).
- [ ] Tell me the affiliate IDs: the hand-off buttons ("Book on Booking.com" etc.) and a setting in
  `backend/.env` for each are **still to build**.

**Charging businesses per guest (to build, then you decide the numbers):**
- [ ] **Decide the fee** (for example €1–3 per redeemed voucher, or a % of the deal price) and put it
  in the Terms for businesses (§5).
- [ ] Until billing is built: invoice monthly from the **Reservations** list in each business's
  dashboard (redeemed vouchers × fee).
- [ ] **To build:** a monthly statement per business from check-ins, a saved card or direct-debit
  mandate at sign-up (Stripe-hosted page, Wayfinder never sees card numbers), and Stripe invoices
  charged automatically. Test mode first.

## 1. Secrets and configuration

Copy `backend/.env.example` to `backend/.env` on the production server and fill in:

| Variable | Required? | Get it from | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | Recommended | platform.openai.com | Powers plain-English trip requests, AI summaries, photo moderation. App works without it (keyword fallback), but noticeably worse |
| `AMADEUS_CLIENT_ID` / `_SECRET` | Optional | developers.amadeus.com | Real flight/hotel **prices and search**. Switch `AMADEUS_BASE_URL` from the test URL to the production one once Amadeus approves you. Do **not** book through it (see §4) |
| `TICKETMASTER_API_KEY` | Optional | developer.ticketmaster.com (free) | Live events |
| `TRAVELPAYOUTS_TOKEN` | Optional | travelpayouts.com (free) | Recent real fares |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Needed to collect Featured-placement fees | stripe.com | Start in **test mode**, confirm a full paid flow works, then switch to your live key. Create the webhook endpoint pointing at `https://<your-domain>/api/payments/stripe/webhook` in the Stripe dashboard to get the webhook secret |
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
- [x] **Dockerfile** (repo root). It builds the frontend and runs the backend in one image, as a non-root
  user, with a health check. Tested locally, offline: the pages, API and trip planner all respond.
  ```
  docker build -t wayfinder .
  docker run -p 8000:8000 --env-file backend/.env \
    -v wayfinder-data:/app/backend/data -v wayfinder-logs:/app/backend/logs wayfinder
  ```
  Most hosts (Railway, Render, Fly.io) detect the Dockerfile automatically; give them the `.env` values as
  secrets in their dashboard, never as a file in the image. Demo data (`backend/data`) is not in the image.
- [x] **Python dependencies are pinned** in `backend/requirements.txt`. An unpinned install pulled `mcp` 2.x
  and the server would not start. Upgrade on purpose: bump a pin, run `pytest`, then deploy.
- [x] **Database upgrades run by themselves** at start-up (new columns are added to an older database,
  existing data kept). Still: take a backup before every deploy (§3).
- [ ] **Put it behind HTTPS.** A reverse proxy (Caddy or nginx with Let's Encrypt, or your PaaS's
  built-in TLS) in front of port 8000. Real push notifications and the installable-app manifest
  both require HTTPS (or `localhost`, which production isn't).
- [ ] **Buy and point a domain** at the host. Update anything that assumes `localhost:8000`.
- [ ] **Persistent disk for `backend/data/`** (the SQLite file, partner/People photos). If your
  host's filesystem is ephemeral (most PaaS free tiers), attach a persistent volume or you will
  lose every account, deal and reservation on the next deploy.
- [ ] **A CI step (or a pre-deploy script) that runs `npm run build` and `pytest`** before every
  deploy, so a broken build or a failing test never reaches production.

## 3. Data and backups

- [ ] **Back up `backend/data/partners.db`** on a schedule (a daily cron copying it to S3/Backblaze
  is enough at this scale), and before every deploy. It now holds partners, deals, People accounts,
  reservations and voucher check-ins. Right now a lost disk means a lost database.
- [x] **PostgreSQL support is built** (F-213): set `WAYFINDER_DATABASE_URL=postgresql://…` and the server uses
  it; schema changes are numbered migrations (F-214). The whole test suite passes on both databases:
  `sh scripts/test_postgres.sh` (from `backend/`) runs it on Postgres in Docker.
- [ ] **Create a managed PostgreSQL database** (Neon, Supabase, Render, Railway, AWS RDS, …) with automatic
  daily backups, in the same region as your server. Put its URL only in the production `.env`.
- [ ] **Move your data once:** `WAYFINDER_DATABASE_URL=… python scripts/migrate_sqlite_to_postgres.py`
  (F-215). On a copy of today's database it copied every business, deal and account and skipped 38
  orphaned rows left by old deletions. Then start the server with the URL set, and keep the SQLite file
  as a backup.
- [ ] **Photos to object storage:** People and business photos are still files in `backend/data/`. Move them
  to S3 or Cloudflare R2 before running more than one server (not built).
- [ ] **Rate limits currently live in memory** (`app/partners/security.py`), so they reset on every
  restart and don't share state across multiple server instances. Fine for one process; revisit if
  you ever run more than one.
- [x] **Trips are kept with the account when signed in** (F-216): trips, day plans, moods, bookings and deal
  vouchers sync across devices. Without an account they still live only in the browser, and the app says so.
- [ ] **Traveler names typed at checkout stay on the device** by design (F-217). When real bookings exist,
  traveler details must be stored server-side, encrypted, and covered by the privacy policy. **Lawyer.**
- [ ] **Password reset** is still missing (§5): with trips now in accounts, a forgotten password means
  losing access to them. Build it before inviting real travelers to create accounts.
- [ ] Deal bookings made **before 25 Sep 2026** never stored their voucher on the server, so a
  business can't look them up by voucher. Clear old test bookings before launch (§8).

## 4. Bookings and suppliers (what's demo today, what replaces it)

Every booking in the app is a **labelled demo**: nothing is reserved and nothing is charged. Each
row needs a real seller before launch, and the demo labels stay until it has one.

| Part | Today | For production |
|---|---|---|
| Flights | Search: Amadeus (with keys) or estimates. Booking: demo checkout | Keep Amadeus for **search and prices**. Book via a hand-off (flight affiliate) or **Duffel**. Booking through Amadeus would mean taking payment yourself, a consolidator or IATA accreditation to issue tickets, and card-security (PCI) duties — not at this stage |
| Hotels | OpenStreetMap hotels, estimated prices (Amadeus offers with keys). Booking: demo | **Booking.com affiliate** hand-off, or Expedia Rapid for in-app booking with Expedia as the seller |
| Activity tickets | Prices are **estimates** from the guide; ticket codes are made up by us | Viator/GetYourGuide prices and hand-offs; drop the demo "Update tickets" charges or turn them into hand-offs |
| Partner deals | Book now → voucher → business checks it in (**built**) | Keep "pay at the place". **Hide "Now, in the app"** until Stripe Connect is built |
| Whole-trip checkout (`/book`) | One demo checkout for flight, stay and tickets | Becomes a list of hand-offs, one per supplier, while Wayfinder keeps the plan, reminders and vouchers together |

- [ ] **Amadeus production access:** apply, then switch `AMADEUS_BASE_URL`. Check their current
  production and booking terms first (they change).
- [ ] **Re-check prices before any hand-off:** fares change by the minute; show "price may change on
  the partner's site" on every hand-off.
- [ ] **Affiliate disclosure:** tell travelers plainly that Wayfinder may earn a commission on
  bookings made through its links (a footer line and a line on each hand-off). **Lawyer.**
- [ ] **Never sell flight + hotel together as one purchase** while you are not a licensed travel
  organiser: in the EU and UK that can make you a package organiser (Package Travel Directive, ATOL)
  with insolvency protection and full liability. Hand-offs per part avoid it. **Lawyer.**
- [ ] **Never store card numbers.** Only hosted pages (Stripe, suppliers) ever see them.

## 5. Legal and trust & safety

- [ ] **Privacy Policy and Terms of Service**, linked from sign-up on both Wayfinder People and the
  partner portal. You are a data controller under GDPR/CCPA the moment a real photo, message or
  reservation is stored. Cover: People profiles and photos, rounded locations, trip data kept in the
  browser, reservations and vouchers (businesses never see who booked), weather and map lookups,
  analytics events, affiliate links. **Lawyer.**
- [ ] **Terms for businesses:** listing rules, the per-guest fee and how it's counted (redeemed
  vouchers), invoicing and payment terms, Featured placements, deal honesty (real usual price),
  and that ranking is never influenced by payment. **Lawyer.**
- [ ] **Consumer rules for deals:** the "usual price" a business enters is shown as a discount; make
  businesses confirm it's genuine (it's in the review queue, keep reviewing it).
- [ ] **Age verification is currently self-declared** (a birth year, a checkbox). Depending on your
  target markets, a legal review of whether that's sufficient for a stranger-meetup feature is
  worth doing before wide launch — see [09 · People and safety §6](09-people-and-safety.md).
- [ ] **Email verification and password reset don't exist yet** — both need an email service
  (Postmark, SendGrid, AWS SES are common free-tier options). "Change my password while signed in"
  is built; "I forgot my password" is not. Businesses need it too (they sign in to check vouchers in).
- [ ] **Decide your moderation capacity.** Photos, reports and new deals queue at `/admin`; with an
  `OPENAI_API_KEY` set, obviously-bad photos are auto-rejected, but someone still has to look at
  the queue regularly, especially early on.
- [ ] **Check the emergency numbers table** (`backend/app/social/emergency.py`, 58 countries) line by
  line against each government's own page. The numbers are shown in the app (F-171) and are the widely
  published ones, but a wrong number here is worse than none. Update `VERIFIED` when done.

## 6. Free data services: licences before commercial use

The app runs on free services that are fine for a demo and some of which forbid commercial use.
Details: [05 · Live data and AI §7](05-live-data-and-ai.md).

- [ ] **Open-Meteo** (season chart and the trip-day forecast): free for **non-commercial** use only.
  Buy their commercial plan (or switch provider) before launch.
- [ ] **Map tiles** (`tile.openstreetmap.org`, used by every map): fair use only, not for production
  traffic. Switch `TILES` in `frontend/src/components/MapView.jsx` to a tile provider (for example
  MapTiler, Stadia Maps, Thunderforest) with its own key and attribution.
- [ ] **Nominatim and Overpass** (hotels, restaurants, business address lookup): public servers
  with strict usage policies (Nominatim at most 1 request per second). Fine with the app's caching at
  small scale; move to a paid or self-hosted instance before real traffic.
- [ ] **Wikipedia and Wikimedia Commons:** free with attribution (already shown on every photo and
  sight). Keep it that way. The app's `User-Agent` (`backend/app/live/http.py`) identifies it with a
  contact address, as their policies ask; it currently says "WayfinderPrototype … demo" with your
  personal email, so change it to your product name and a business contact address.
- [ ] **Ticketmaster, Amadeus, Travelpayouts:** read each one's display and attribution rules and
  quotas before production (Ticketmaster attribution is already shown).
- [ ] **OpenAI:** set a monthly spending limit in your OpenAI account.

## 7. Payments (Stripe: businesses paying you, never travelers)

- [ ] Create your Stripe account, verify it (Stripe asks for real business and bank details before
  paying out to you).
- [ ] Start in Stripe **test mode**: set `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` to the test
  values, register a test partner account, click "Feature this deal," and pay with Stripe's test
  card `4242 4242 4242 4242` end to end. Confirm the deal actually shows "Featured" afterward.
- [ ] Switch to your **live** Stripe keys only once that works, and re-test with a real (small)
  charge.
- [ ] Decide your refund policy for a featured placement and be ready to issue one manually from
  the Stripe dashboard — there's no in-app refund flow yet.
- [ ] **Later (to build): Stripe Billing** for the per-guest fees (§0): saved payment method at
  business sign-up, monthly statement from check-ins, automatic invoices.
- [ ] **Much later, only if travelers ask to pay in one place:** Stripe Connect for partner deals
  (each business connects its own Stripe account; Stripe pays them minus your commission). A
  materially bigger project: business onboarding and identity checks, payouts, refunds, terms.

## 8. Demo content to remove before real users

- [ ] **Demo businesses and their deals:** `python scripts/seed_demo.py --remove` (from `backend/`).
- [ ] **Demo travelers in People:** `python scripts/seed_people.py --remove`.
- [ ] **Test reservations, bookings and accounts** you created while trying things (a fresh
  production database avoids all of this: don't copy your laptop's `backend/data` to the server).
- [ ] **Demo labels** ("Demo booking", "demo" on payments) stay until the real seller for that part
  exists (§4); remove each one only when its hand-off or payment is real.

## 9. Analytics and monitoring

- [ ] The built-in `/admin` analytics dashboard works with zero setup: sign-ups, People and partner
  funnels, and the booking funnel. Nothing to do here to get basic numbers.
- [ ] **No error tracking or uptime monitoring exists.** Add one (Sentry's free tier for errors, a
  free uptime pinger like UptimeRobot for availability) before you have real users depending on
  the app being up.
- [ ] **No structured application logs beyond the two markdown activity logs** (`backend/logs/`).
  Fine at this scale; if you outgrow it, ship logs somewhere queryable (even just journald + `grep`
  on the VM is enough for a while).
- [ ] **Track what you'll bill and show investors:** redeemed vouchers per business per month (in
  each business's Reservations list today; a monthly statement is still to build, §0).

## 10. Final pre-launch pass

- [ ] Run the full test suite one more time on the production branch: `cd backend && python -m
  pytest` — every test should pass.
- [ ] Run `python scripts/sync_docs.py` (from `backend/`) and confirm `git status` shows no
  changes (docs match code).
- [ ] Load the production URL on an actual phone, not just a laptop browser — check the install
  prompt, push permission prompt, bottom nav, a voucher check-in from a second phone, and a map.
- [ ] Go through §4 row by row: every place a traveler can "book" either hands off to a real seller
  or still says "demo".
- [ ] Re-read [09 · People and safety §6](09-people-and-safety.md) ("What is not built") one more
  time immediately before letting real strangers message each other.
