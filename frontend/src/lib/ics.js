/** A calendar file (.ics) for a booked trip: the flights, the stay and every planned activity, in local time. */
import { PART_LABEL, PART_TIME } from "./dayplan";

// RFC 5545 text escaping: backslash, comma and semicolon get a backslash; a newline becomes the two characters \n.
const esc = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/[,;]/g, (c) => `\\${c}`).replace(/\n/g, "\\n");
const ymd = (iso) => iso.replaceAll("-", "");
const addDays = (iso, n) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const at = (iso, hhmm) => `${ymd(iso)}T${hhmm.replace(":", "")}00`;
const plusHours = (hhmm, h) => {
  const [H, M] = hhmm.split(":").map(Number);
  return `${String(Math.min(23, H + h)).padStart(2, "0")}:${String(M).padStart(2, "0")}`;
};

export function tripCalendar({ reference, req, cityFrom, cityTo, hotel, flight, items, booking }) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  const events = [];
  const add = (uid, start, end, summary, description, allDay = false) => events.push([
    "BEGIN:VEVENT", `UID:${reference}-${uid}@wayfinder`, `DTSTAMP:${stamp}`,
    allDay ? `DTSTART;VALUE=DATE:${ymd(start)}` : `DTSTART:${start}`,
    allDay ? `DTEND;VALUE=DATE:${ymd(end)}` : `DTEND:${end}`,
    `SUMMARY:${esc(summary)}`, `DESCRIPTION:${esc(description)}`, "END:VEVENT",
  ].join("\r\n"));

  const demo = `Wayfinder demo booking ${reference}. Nothing is reserved or charged.`;
  const dep = flight.depart_time || "09:00";
  add("out", at(req.start_date, dep), at(req.start_date, plusHours(dep, 3)), `✈ ${cityFrom} → ${cityTo}`, `${flight.airline || "Flight"} · PNR ${booking.flight.pnr}. ${demo}`);
  add("stay", req.start_date, req.end_date, `🏨 ${hotel.name}`, `Confirmation ${booking.stay.confirmation}. ${demo}`, true);
  items.forEach((i, n) => {
    const date = addDays(req.start_date, i.day - 1);
    const t = PART_TIME[i.part];
    const ticket = booking.tickets.find((x) => x.name === i.name);
    add(`a${n}`, at(date, t), at(date, plusHours(t, 2)), i.name, `${PART_LABEL[i.part]}${ticket ? ` · ticket ${ticket.code}` : ""}. ${demo}`);
  });
  add("home", req.end_date, addDays(req.end_date, 1), `✈ ${cityTo} → ${cityFrom}`, `Return flight. ${demo}`, true);
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Wayfinder AI//Demo booking//EN", "CALSCALE:GREGORIAN", ...events, "END:VCALENDAR"].join("\r\n");
}

export function downloadCalendar(text, name) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/calendar" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
