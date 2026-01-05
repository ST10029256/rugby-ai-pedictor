// Date helpers used for stable keys and UI when a match date is missing.
// NOTE: `Date.toISOString()` returns UTC, which can shift the day near midnight in local time.

export function getLocalYYYYMMDD(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  const tzOffsetMinutes = d.getTimezoneOffset();
  const local = new Date(d.getTime() - tzOffsetMinutes * 60 * 1000);
  return local.toISOString().slice(0, 10);
}


