/* Thin fetch wrapper. Every call returns parsed JSON or throws with the
   server's own detail message, so the UI can surface something useful. */

async function call(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail);
      }
    } catch { /* response had no JSON body */ }
    throw new Error(detail);
  }
  return res.json();
}

const post = (path, body) => call(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const api = {
  health:       ()      => call('/api/health'),
  models:       ()      => call('/api/models'),
  neos:         (q, n)  => call(`/api/neos?search=${encodeURIComponent(q || '')}&limit=${n || 60}`),
  sentry:       (n)     => call(`/api/sentry?limit=${n || 40}`),
  terrain:      (la, lo)=> call(`/api/geo/terrain?lat=${la}&lon=${lo}`),
  effects:      (b)     => post('/api/effects', b),
  simulateSimple:(b)    => post('/api/simulate/simple', b),
  simulateElements:(b)  => post('/api/simulate/elements', b),
};
