// JSON API client. Errors surface the server's message.

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function call(method, url, body, { raw = false } = {}) {
  const opts = { method, headers: {}, credentials: "same-origin" };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, opts); }
  catch (e) { throw new ApiError(0, "Cannot reach the studio server. Is it still running?"); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return raw ? res : res.json();
}

export const api = {
  get: (u) => call("GET", u),
  post: (u, b) => call("POST", u, b ?? {}),
  put: (u, b) => call("PUT", u, b),
  patch: (u, b) => call("PATCH", u, b),
  raw: (u) => call("GET", u, undefined, { raw: true }),
};
