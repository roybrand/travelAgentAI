# 08 · API reference (generated)

> **Generated from the code. Do not edit by hand.** Run `python scripts/sync_docs.py` from `backend/` after
> adding or changing an endpoint, a nearby rule, an environment variable or a page. A test fails when this
> file is out of date, so it cannot silently drift.

For what each feature means and who it is for, see the [feature registry](FEATURES.md).

## Endpoints

| Method | Path | Who can call it | What it does |
|---|---|---|---|
| GET | `/api/admin/deals` | Admin token | Deals waiting for review, with reviewer flags. |
| POST | `/api/admin/deals/{deal_id}/approve` | Admin token | Approve a pending deal so travelers can see it. |
| POST | `/api/admin/deals/{deal_id}/reject` | Admin token | Reject a pending deal with a reason the business will see. |
| GET | `/api/admin/partners` | Admin token | Every partner with deal, view and click totals. |
| POST | `/api/admin/partners/{partner_id}/status` | Admin token | Suspend or reinstate a partner. Suspension hides their deals and blocks sign-in. |
| GET | `/api/admin/people/photos` | Admin token | Profile photos waiting for a human decision. |
| POST | `/api/admin/people/photos/{user_id}/approve` | Admin token | Approve a pending profile photo. |
| POST | `/api/admin/people/photos/{user_id}/reject` | Admin token | Reject a pending profile photo and delete the file. |
| GET | `/api/admin/people/reports` | Admin token | Open reports against people, with how many are open against each person. |
| POST | `/api/admin/people/reports/{report_id}/resolve` | Admin token | Close a report, optionally banning the person (their sessions end at once). |
| POST | `/api/build-trip` | Public | Trip fields plus a traveler profile (keywords, interests, place types) from free text and/or a photo. |
| GET | `/api/config` | Public | What is switched on, so the UI can show or hide features and label data sources honestly. |
| GET | `/api/deals` | Public | Approved partner deals for a destination, ranked by match to the traveler. |
| GET | `/api/deals/options` | Public | The category, tag and currency lists for the deal form, and the public disclosure text. |
| POST | `/api/deals/{deal_id}/click` | Public | Count one click on a deal's booking link (shown to the business as a result). |
| GET | `/api/destinations` | Public | The 100 selectable destinations (Europe, Americas, Asia). |
| GET | `/api/events` | Public | Live events near a destination during the trip (needs a free Ticketmaster key). |
| POST | `/api/nearby` | Public | Dynamic recommendations around a GPS position, using the weather, time of day, interests and trip plan. |
| POST | `/api/parse-request` | Public | Turn a plain-English trip description into form fields (needs OPENAI_API_KEY). |
| POST | `/api/partner-feed` | API key | Bulk create/update deals with an API key. Each item needs a stable external_id and an explicit valid_from. Items go through the same validation and review as deals typed into the portal. |
| POST | `/api/partners/api-key` | Partner sign-in | Create or replace the feed API key. The key is shown once. |
| POST | `/api/partners/deals` | Partner sign-in | Submit a new deal. It waits for moderator review before travelers see it. |
| DELETE | `/api/partners/deals/{deal_id}` | Partner sign-in | End one of the partner's deals for good. |
| PUT | `/api/partners/deals/{deal_id}` | Partner sign-in | Edit a deal. Changed content goes back to review; identical content stays live. |
| POST | `/api/partners/deals/{deal_id}/pause` | Partner sign-in | Pause or resume one of the partner's deals. |
| GET | `/api/partners/geocode` | Partner sign-in | Find coordinates for a street address, near the chosen city (OpenStreetMap Nominatim, free). |
| POST | `/api/partners/login` | Public | Sign in a partner. Rate limited. |
| POST | `/api/partners/logout` | Partner sign-in | End the current partner session. |
| GET | `/api/partners/me` | Partner sign-in | The signed-in partner's profile, totals, and every deal with its views and clicks. |
| POST | `/api/partners/register` | Public | Create a partner account and sign in. |
| POST | `/api/people/attend` | Partner sign-in | Register to a place for a day: 'I am going'. Others going there can see my profile if it is visible. |
| DELETE | `/api/people/attend/{attendance_id}` | Partner sign-in | Cancel a registration. |
| GET | `/api/people/attendees` | Partner sign-in | Who is going to a place on a day (discoverable people only, never anyone who blocked or was blocked). |
| POST | `/api/people/block` | Partner sign-in | Block someone: you disappear from each other everywhere and any chat closes. |
| GET | `/api/people/chats/{connection_id}/messages` | Partner sign-in | Messages in a chat, newer than `after`. The app polls this every few seconds while a chat is open. |
| POST | `/api/people/chats/{connection_id}/messages` | Partner sign-in | Send a message in an accepted chat. |
| POST | `/api/people/connect` | Partner sign-in | Ask to connect. Chat opens only if the other person accepts. |
| GET | `/api/people/connections` | Partner sign-in | Requests I received, requests I sent, and my open chats. |
| POST | `/api/people/connections/{connection_id}/respond` | Partner sign-in | Accept or decline a request I received. |
| GET | `/api/people/counts` | Public | How many discoverable people are going to each place on a day. Numbers only, so no sign-in is needed. |
| POST | `/api/people/login` | Public | Sign in a traveler. Rate limited. |
| POST | `/api/people/logout` | Partner sign-in | End the current session. |
| POST | `/api/people/looking` | Partner sign-in | Describe an activity and the company you want. The AI reads it into tags, and we return matching people nearby. |
| DELETE | `/api/people/looking/{intent_id}` | Partner sign-in | Close one of my requests so I stop showing up in other people's matches. |
| GET | `/api/people/looking/{intent_id}/matches` | Partner sign-in | Refresh the matches for one of my open requests. |
| GET | `/api/people/me` | Partner sign-in | My profile, my plans, my open requests and the people I have blocked. |
| PATCH | `/api/people/me` | Partner sign-in | Edit my profile, or hide it from everyone with visible=false. |
| POST | `/api/people/me/delete` | Partner sign-in | Delete my account and everything attached to it: messages, requests, plans and photo. |
| DELETE | `/api/people/me/photo` | Partner sign-in | Remove my profile photo. |
| POST | `/api/people/me/photo` | Partner sign-in | Upload a profile photo (a small JPEG, PNG or WebP). Others see it only after it is approved. |
| GET | `/api/people/options` | Public | Activity, language and vibe lists for profiles and requests, and the community rules. |
| GET | `/api/people/photo/{name}` | Public | A profile photo. The address is a random 128-bit name that is only shown to people who may see the photo. |
| POST | `/api/people/register` | Public | Create a traveler account. Adults only: the person confirms they are 18 or older and accepts the rules. |
| POST | `/api/people/report` | Partner sign-in | Report a person (optionally a message) to the moderators. |
| POST | `/api/people/unblock` | Partner sign-in | Undo a block. |
| POST | `/api/plan-trip` | Public | Plan a trip: flights, stays, ranking, guide, packages, partner deals and an optional AI summary. |
| GET | `/api/tonight` | Public | The best clubs and bars in a city for one night, with photos, opening hours, and real prices where they exist. |
| GET | `/health` | Public | Liveness check used by the UI status pill. |

## Front-end pages

| Path |
|---|
| `/` |
| `/trip` |
| `/stays` |
| `/explore` |
| `/nearby` |
| `/tonight` |
| `/people` |
| `/deals` |
| `/partners` |
| `/admin` |
| `/credits` |

## Nearby-engine rules

| Rule | What it does |
|---|---|
| DYN-01 | Plan proximity: something from your trip plan is close to you right now |
| DYN-02 | Rain expected or falling: indoor places are pushed up, open-air places down |
| DYN-03 | Good weather: parks, viewpoints and waterfronts are pushed up |
| DYN-04 | Breakfast time: cafes are pushed up |
| DYN-05 | Lunch time: restaurants are pushed up |
| DYN-06 | Evening: restaurants and bars are pushed up (bars more if you like nightlife) |
| DYN-07 | Interest match: places that fit what you said you like are pushed up |
| DYN-08 | Distance: nearer places rank higher, with a walking-time estimate |
| DYN-09 | Popularity: among sights, more-read Wikipedia articles rank higher |
| DYN-10 | No repeats: the app only pushes a recommendation it has not already shown this session |
| DYN-11 | Partner deal in reach: a reviewed partner deal nearby ranks by interest match, real discount and distance, never by payment, and is always labelled |
| DYN-12 | Ends soon: a deal ending today or tomorrow is nudged up a little, as information rather than pressure |
| DYN-13 | Live event: an event starting within the next few hours close to you (needs a free Ticketmaster key) |

## Environment variables

Set these in `backend/.env` (copy from `.env.example`).

| Variable | Notes |
|---|---|
| `OPENAI_API_KEY` | Optional: plain-English trip requests and grounded explanations |
| `OPENAI_MODEL` | - |
| `OPENAI_BASE_URL` | Optional: an OpenAI-compatible endpoint (proxy, Azure, local test server) |
| `AMADEUS_CLIENT_ID` | Optional: real flight and hotel offers (free signup at https://developers.amadeus.com) |
| `AMADEUS_CLIENT_SECRET` | - |
| `AMADEUS_BASE_URL` | Free test environment by default; switch to https://api.amadeus.com once you have production access |
| `TICKETMASTER_API_KEY` | Optional: live events and parties (free key at https://developer.ticketmaster.com) |
| `TRAVELPAYOUTS_TOKEN` | Optional: recent real flight fares (free affiliate signup at https://www.travelpayouts.com) |
| `ADMIN_TOKEN` | Partner portal: a long random string that unlocks the moderation page at /admin. Leave empty to disable it. |
| `WAYFINDER_DB` | Where partner accounts and deals are stored (SQLite). Default: backend/data/partners.db |
| `WAYFINDER_OFFLINE` | Set to 1 to disable all network calls and use built-in demo data |
