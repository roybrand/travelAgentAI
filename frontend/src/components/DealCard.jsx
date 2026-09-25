import { trackDealClick } from "../api";
import { TAG_LABEL } from "../lib/constants";
import { longDate, metres, money } from "../lib/format";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import Photo from "./Photo.jsx";
import { useDealBooking } from "../state/DealBookingContext.jsx";

const label = (k) => TAG_LABEL[k] || PLACE_TYPE_LABEL[k] || k;

export const CATEGORY_ICON = { hotel: "🛏️", restaurant: "🍽️", bar: "🍸", party: "🎉", tour: "🧭", activity: "🎟️", spa: "💆", car_rental: "🚗", flight: "✈️" };

/** The badge that marks paid or partner content. It appears on every partner deal, everywhere. */
export function PartnerBadge() {
  return <span className="badge partner" title="Set by the business and reviewed by us. Never ranked by payment.">Partner deal</span>;
}

/** Marks a deal shown in the Featured strip: the business paid for this placement. It never affects the
 * payment-blind ranking used everywhere else -- Featured is always its own separate, labelled strip. */
export function FeaturedBadge() {
  return <span className="badge gold" title="This business paid to appear in the Featured strip. It never changes how deals are ranked.">★ Featured</span>;
}

function priceText(n, currency) {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency, minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 }).format(n);
}

/** A partner deal. `preview` disables tracking so the partner form can show a live preview. */
export default function DealCard({ deal, preview = false }) {
  const booking = useDealBooking();
  const open = () => {
    if (!preview && deal.id) trackDealClick(deal.id);
  };
  const aiPhoto = deal.photo_url?.startsWith("/api/deals/business-photo/");
  return (
    <article className="card deal">
      <Photo src={deal.photo_url} alt={deal.title} className="deal-photo">
        {!deal.photo_url && <span className="rec-icon">{CATEGORY_ICON[deal.category] || "🏷️"}</span>}
        <span className="badges"><PartnerBadge />{deal.featured && <FeaturedBadge />}</span>
        {aiPhoto && <i className="ai-mark" title="An AI photo of a generic, fictional venue for this category — not a photograph of this business">AI</i>}
        {deal.discount_pct >= 10 && <span className="badge deal deal-pct">−{deal.discount_pct}%</span>}
      </Photo>
      <div className="deal-body">
        <div className="deal-meta">
          <span className="fpill">{deal.category_label}</span>
          {deal.city && <span className="fpill">{deal.city}</span>}
          {deal.distance_m != null && <span className="fpill">{metres(deal.distance_m)} away</span>}
        </div>
        <h3>{deal.title}</h3>
        <p className="muted">{deal.description}</p>
        <div className="deal-price">
          <b>{priceText(deal.price, deal.currency)}</b>
          {deal.reference_price && <s>{priceText(deal.reference_price, deal.currency)}</s>}
          {deal.price_note && <span>{deal.price_note}</span>}
        </div>
        {(deal.match?.length > 0 || deal.why?.length > 0) && (
          <div className="facts-row">
            {deal.match?.map((t) => <span key={t} className="tag hit">★ {label(t)}</span>)}
            {deal.why?.filter((w) => w !== "Matches what you like").map((w) => <span key={w} className="tag">{w}</span>)}
          </div>
        )}
        <p className="fine deal-fine">
          Offered by <b>{deal.partner_name}</b>
          {deal.valid_to && <> · valid until {longDate(deal.valid_to)}</>}
          {deal.address && <> · {deal.address}</>}
          {deal.stock != null && <> · {deal.stock} available (per the business)</>}
        </p>
        <details className="terms">
          <summary>Terms</summary>
          <p>{deal.terms}</p>
        </details>
        <div className="deal-actions">
          {!preview && booking && <button type="button" className="btn primary sm" onClick={() => booking.open(deal)}>Book now</button>}
          <a className={`btn ${preview ? "primary" : "ghost"} sm`} href={preview ? undefined : deal.url} target="_blank" rel="noopener noreferrer sponsored" onClick={open}>
            Get this deal ↗
          </a>
        </div>
      </div>
    </article>
  );
}

/** A live event from Ticketmaster, with the required attribution and a link to the official page. */
export function EventCard({ event }) {
  const when = [longDate(event.date), event.time].filter(Boolean).join(" · ");
  return (
    <article className="card deal event">
      <Photo src={event.photo_url} alt={event.title} className="deal-photo">
        {!event.photo_url && <span className="rec-icon">🎟️</span>}
        <span className="badges"><span className="badge gold">{event.category}</span></span>
      </Photo>
      <div className="deal-body">
        <h3>{event.title}</h3>
        <p className="muted">{[event.venue, when].filter(Boolean).join(" · ")}</p>
        {event.price_min != null && <div className="deal-price"><span>From</span><b>{money(event.price_min, event.currency || "GBP")}</b></div>}
        <a className="btn ghost sm" href={event.url} target="_blank" rel="noopener noreferrer">Tickets on Ticketmaster ↗</a>
      </div>
    </article>
  );
}
