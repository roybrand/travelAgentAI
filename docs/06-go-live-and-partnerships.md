# 06 · Go live: requirements, partners and the phone process

Written for the founder. It lists exactly what has to be done to move Wayfinder from a working
prototype to a live product with real-time prices and business-pushed deals.

> **Check terms before you commit.** Provider programs, prices and approval rules change. Everything
> below is the usual route as of writing. Confirm each one on the provider's own site before you rely on it.

## 0. Where you are today

| Area | State |
|---|---|
| App, 109 destinations, AI trip builder, nearby engine | Working locally |
| Weather, sights, photos, hotels and restaurants | Real, free sources (Open-Meteo, Wikipedia, OpenStreetMap) |
| Flight and stay **prices** | Labelled estimates |
| Amadeus, Ticketmaster and Travelpayouts adapters | Written and unit-tested, never run against real keys |
| Business accounts, deals database, partner portal, moderation, feed API | **Built** (see [07](07-partner-portal-and-deals.md)), on SQLite |
| Real payment: Featured deal placements | **Built** (Stripe Checkout, no SDK), off until a Stripe key is set — the first real revenue line |
| Real push notifications, even while closed | **Built** (Web Push, RFC 8291/8292, no SDK), off until a VAPID key pair is set |
| Self-hosted analytics (signups, connections, messages, funnels) | **Built**, in `/admin`, no vendor |
| Auth hardening: common-password denylist, per-account rate limiting, change password | **Built** |
| Hosting, HTTPS, domain, company | **Not done** |
| OpenAI key | In `backend/.env`. It was pasted in chat, so **rotate it** |

## 1. The demands, in order

Do these in this order. Each step unlocks the next.

### Step A. Company and basics (week 1)

- [ ] Register a company (a limited company or your local equivalent). Suppliers and payment providers ask for one.
- [ ] Open a business bank account.
- [ ] Buy a domain and a business email on it (`partners@yourdomain`). Applications from a free email are often rejected.
- [ ] Write a one-page privacy policy and terms of use. A template plus a lawyer's review is enough to start.
- [ ] Put the app on a public URL (Step D) so applications have something to point to.

### Step B. Apply for real-time data (week 1, in parallel)

Apply to several at once. Approvals take days to weeks.

- [ ] **Travelpayouts** (flights, hotels, cars, tours, one signup).
- [ ] **Awin** and **Impact** (Booking.com, Expedia and many car rental and tour brands run programs there).
- [ ] **Amadeus for Developers**: request production access for flights and hotels.
- [ ] **Duffel** (flights): instant signup, pay per booking.
- [ ] **Ticketmaster Discovery API**: free key, covers events and concerts.
- [ ] **Viator** and **GetYourGuide** partner programs (tours and activities).

What each application usually asks for: company details, the live URL, a description of your audience,
and a privacy policy. Say clearly that you are a trip-planning product that links out to book.

### Step C. Pilot partners by hand (weeks 2–6)

Pick **one city** (for example the one you know best). Sign **5–10 real businesses** yourself:
2 hotels, 2 restaurants or pubs, 1 car rental, 1 tour or activity, 1 bar or club. Enter their deals into
the app manually if the portal is not ready. Investors respond to real partners more than to features.

### Step D. Deploy (week 2–3)

- [ ] Host the backend and the built front end on one service (Render, Railway, Fly.io or a small VPS).
- [ ] HTTPS on your domain. This is **required** for phone GPS and push notifications.
- [ ] Add a database (Postgres) for accounts, deals and partner data.
- [ ] Set secrets (OpenAI, Amadeus, affiliate IDs) as environment variables on the host, never in the repo.
- [ ] Add monitoring, backups and rate limiting.

### Step E. Build the partner side (weeks 3–8)

- [ ] Partner sign-up and email verification.
- [ ] Deal form: title, price, reference ("was") price, dates, terms, stock, photos, location.
- [ ] Moderation queue: a person approves a deal before it goes live.
- [ ] Partner API with keys and webhooks, for chains and airlines that push feeds.
- [ ] Deal expiry when stock runs out or the date passes.
- [ ] "Partner deal" badge on every paid or partner deal.
- [ ] Partner deals feed the ranking and the nearby engine.

## 2. Who to partner with

### Real-time data (pull)

| Need | Partner | How to start | Cost model |
|---|---|---|---|
| Flights and hotels | Amadeus Self-Service | Production request on their portal | Free test quota, then per call |
| Flights | Duffel | Instant signup | Per booking |
| Flights, hotels, cars, tours (aggregated) | Travelpayouts | Signup, then apply per brand | Commission |
| Hotels | Booking.com (via Awin or Impact, or the Demand API) | Affiliate application | Commission |
| Hotels | Expedia Group (Rapid API or affiliate) | Partner application | Commission |
| Car rental | Cartrawler, Discover Cars, Rentalcars (affiliate) | Affiliate application | Commission |
| Events, concerts, parties | Ticketmaster Discovery API | Free API key | Free, commission on affiliate links |
| Tours and activities | Viator, GetYourGuide, Klook | Partner application | Commission |
| Restaurants | Google Places (paid), Yelp Fusion, TheFork or OpenTable partner programs | Key or partner application | Per call or commission |

### Turning the demo booking into a real one

The booking flow (review, travelers, payment, confirmation, cancel) is already built as a demo in `app/bookings.py`.
Going live means replacing its one `confirm()` function with real calls: a flight order (Duffel or Amadeus), a hotel
booking (a bed bank or the Booking.com/Expedia partner APIs), activity tickets (Viator, GetYourGuide) and Stripe
Checkout for the payment, which the partner side already uses. Traveler names and passports would then have to be
sent to those suppliers, so the privacy policy must cover it. Until then, every screen says it is a demo.

### How money moves for partner deals

Today no money moves through Wayfinder. A traveler books a deal as a demo and chooses to pay at the place (the default)
or in the app. The business sees the reservation in its dashboard and checks the voucher in at the door (pay at the
place is fully built, business side included). Taking real payment in the app would use Stripe Connect: each business
connects its own Stripe account, the traveler pays in the app, and Stripe pays the business minus a commission. That
needs business onboarding (identity checks), payouts, refunds and terms, and is not built.

### Businesses that push deals (push)

| Type | Who to approach first | The pitch |
|---|---|---|
| Independent hotels and guesthouses | Owners and managers, not chains | Fill empty nights with a targeted deal to travelers already planning that city |
| Restaurants, pubs, bars | Owners | A quiet-night or happy-hour deal shown to nearby opted-in travelers |
| Car rental (local firms) | Local independents | Fill idle cars at short notice |
| Tour and activity operators | Small operators | Last-minute seats |
| Clubs, party and event promoters | Promoters | Reach visitors the night they arrive |
| Airlines and chains | Later, via their affiliate or partner teams | They will not sign with an unproven app, so start with the affiliate route |

What to offer, in plain terms: **no upfront fee for the pilot**, you show their deal to the right
people, and you take a commission only on bookings you send.

## 3. The phone process

This covers both meanings of "phones": how travelers get deals on their phone, and how you reach businesses by phone.

### 3a. Deals on the traveler's phone

Today the nearby engine works only in a browser and only while the page is open. To reach phones properly:

1. **HTTPS first.** Browsers block location and notifications on plain HTTP (except `localhost`).
2. **Make it installable (PWA).** Add a web app manifest and a service worker. Users tap "Add to Home Screen" and it behaves like an app. No app store needed.
3. **Web Push.** With a service worker and a VAPID key pair, the server can send notifications when the app is closed. Works on Android and on iPhone (iOS 16.4+, only after the app is added to the Home Screen).
4. **Opt-in, always.** Location and notifications each need an explicit yes from the user, with an off switch. This is already the rule for DYN-01..10 and stays the rule.
5. **Server-side matching.** For background push, the phone sends a coarse location or geofence to the server only when the user allows it. The server matches it to live partner deals and pushes one notification. Set a limit, for example a maximum of 3 per day, and quiet hours.
6. **Native apps later.** Only build iOS and Android apps if you need true background location. That means app store accounts (Apple charges an annual fee, Google a one-time fee) and review time.

### 3b. Reaching businesses by phone

A simple, repeatable script for cold calls or walk-ins:

1. **Find them.** Use the app itself. Pick businesses in your pilot city that already appear in the OpenStreetMap results, so you can say, "You are already on our map."
2. **Call or visit** in a quiet hour (mid-morning for restaurants, early afternoon for hotels). Ask for the owner or manager.
3. **Thirty-second pitch:** "We show visitors real places nearby with live deals. It is free to list. You choose the deal, we send you customers, and you pay only if a booking comes from us."
4. **Ask for one thing:** a single deal they would run this week (a discount, a free item, a last-minute room).
5. **Send a follow-up** the same day by email or WhatsApp with a link to the deal form and a screenshot of how it will look.
6. **Log every contact** in a simple sheet: name, business, date, response, next step, deal status.
7. **Review after two weeks:** how many views and clicks their deal got. Send them that number. It is your best sales tool.

## 4. Rules you must follow

| Area | Rule |
|---|---|
| Honesty | Label every partner or sponsored deal. Never let payment silently raise a deal's rank. Rank by match to the traveler. |
| Discounts | The EU and UK have rules on "was/now" pricing. Partners must supply a genuine reference price and the deal must be real. |
| Privacy | GDPR (and local equivalents) once you store accounts. Location and notifications stay opt-in. Store as little as possible. |
| Payments | Deep links to the supplier avoid handling money. If you take payment yourself, use a provider such as Stripe Connect and write refund terms. |
| Data licences | Keep Wikimedia photo credits and OpenStreetMap attribution. Open-Meteo's free tier is non-commercial, so move to its paid plan once the app earns money. |
| Keys | Never commit keys. Rotate any key that has been shared in chat or email. |

## 5. Checklist by week

| Week | Do |
|---|---|
| 1 | Company, bank, domain, email. Rotate OpenAI key. Apply to Travelpayouts, Awin, Impact, Amadeus, Duffel, Ticketmaster |
| 2 | Deploy with HTTPS. Choose the pilot city. Start calling businesses |
| 3–4 | First partner deals in by hand. Add Ticketmaster events and the first affiliate links |
| 4–6 | Build the partner portal, deals database and "Partner deal" badge |
| 6–8 | PWA, web push and server-side nearby matching. First metrics to partners |
| 8+ | Amadeus production prices, more cities, first airline and chain conversations |

## 6. What is already built

Steps in this document marked "build" now exist in the app. See [07 · Partner portal, deals and suppliers](07-partner-portal-and-deals.md).

| Built | Still yours or still to build |
|---|---|
| Partner sign-up, deal form, moderation, feed API, dashboard | Company, bank, domain, business email |
| Deals on the trip page, deals page and Nearby, always labelled | Applications to Travelpayouts, Awin, Impact, Amadeus, Duffel, Ticketmaster |
| Ticketmaster events and Travelpayouts fares (need free keys) | Getting the keys and testing the adapters with them |
| Installable app, and **real background Web Push for a closed phone** (see [09 §8](09-people-and-safety.md#8-real-push-notifications)) | HTTPS hosting (Web Push needs it in production; localhost is exempt) |
| **Featured deal payments** (real Stripe Checkout, see [07](07-partner-portal-and-deals.md#featured-deal-placements)) | A live Stripe account, and Stripe Connect if you later want to pay out to partners directly |
| **Self-hosted analytics dashboard** in `/admin` (signups, connections, messages, two funnels) | A real marketing/acquisition channel to point it at -- there is still no visit-level tracking |
| **Change my password**, a common-password denylist, per-account login rate limiting | Email verification and password *reset* (both need an email service, which does not exist yet) |
| SQLite storage | Postgres and backups once real partners join |
| A moderator check on every deal | Someone to do the reviewing |

The company, applications and calls are yours, and this document is the checklist for them.
