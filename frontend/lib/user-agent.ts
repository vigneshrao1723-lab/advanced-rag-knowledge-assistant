/** Turns a stored session's raw User-Agent string (backend/app/api/v1/auth.py
 * ::_device_label -- truncated, unparsed, exactly as the browser sent it)
 * into a short, human-readable label for display, instead of showing debug-
 * looking raw UA text in the Settings "Active sessions" list. Deliberately a
 * small pattern match, not a dependency -- the raw value is still what's
 * stored and sent by the backend; this only changes how it's rendered. */
export function describeDevice(userAgent: string | null): string {
  if (!userAgent) return "Unknown device";

  let browser = "Unknown browser";
  if (/Edg\//.test(userAgent)) browser = "Edge";
  else if (/OPR\//.test(userAgent)) browser = "Opera";
  else if (/Chrome\//.test(userAgent) && !/Chromium/.test(userAgent)) browser = "Chrome";
  else if (/CriOS\//.test(userAgent)) browser = "Chrome";
  else if (/FxiOS\//.test(userAgent)) browser = "Firefox";
  else if (/Firefox\//.test(userAgent)) browser = "Firefox";
  else if (/Safari\//.test(userAgent) && !/Chrome\//.test(userAgent)) browser = "Safari";

  let os = "Unknown OS";
  if (/iPhone|iPad|iPod/.test(userAgent)) os = "iOS";
  else if (/Android/.test(userAgent)) os = "Android";
  else if (/Mac OS X/.test(userAgent)) os = "macOS";
  else if (/Windows/.test(userAgent)) os = "Windows";
  else if (/Linux/.test(userAgent)) os = "Linux";

  if (browser === "Unknown browser" && os === "Unknown OS") return "Unknown device";
  return `${browser} on ${os}`;
}
