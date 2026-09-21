const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function validateTripRequest(body) {
  const errors = [];

  if (typeof body !== "object" || body === null) {
    return { valid: false, errors: ["Request body must be a JSON object"] };
  }

  const { origin, destination, startDate, endDate, budget, travelers, interests } = body;

  if (!origin || typeof origin !== "string") errors.push("origin is required (string)");
  if (!destination || typeof destination !== "string") errors.push("destination is required (string)");
  if (!startDate || !DATE_RE.test(startDate)) errors.push("startDate is required (YYYY-MM-DD)");
  if (!endDate || !DATE_RE.test(endDate)) errors.push("endDate is required (YYYY-MM-DD)");

  if (startDate && endDate && DATE_RE.test(startDate) && DATE_RE.test(endDate)) {
    if (new Date(endDate) <= new Date(startDate)) {
      errors.push("endDate must be after startDate");
    }
  }

  if (budget !== undefined && (typeof budget !== "number" || budget <= 0)) {
    errors.push("budget must be a positive number when provided");
  }

  if (travelers !== undefined && (!Number.isInteger(travelers) || travelers < 1)) {
    errors.push("travelers must be a positive integer when provided");
  }

  if (interests !== undefined && (!Array.isArray(interests) || !interests.every((i) => typeof i === "string"))) {
    errors.push("interests must be an array of strings when provided");
  }

  if (errors.length > 0) return { valid: false, errors };

  return {
    valid: true,
    errors: [],
    normalized: {
      origin,
      destination,
      startDate,
      endDate,
      budget: budget ?? null,
      travelers: travelers ?? 1,
      interests: interests ?? [],
    },
  };
}
