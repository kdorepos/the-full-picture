import { createClient } from '@vercel/kv';
import { timingSafeEqual } from 'node:crypto';

// Built lazily inside the handler: createClient() throws if the env vars are missing,
// and we want that caught (→ {active:false}) rather than crashing the function at import
// before the KV store is set up. Accepts either naming the storage integration injects.
function kvClient() {
  return createClient({
    url: process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL,
    token: process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN,
  });
}

// Live transcription progress for the homepage "now processing" panel.
//   GET  → the last-pushed progress ({active:false} when idle or KV unset)
//   POST → the pipeline pushes an update (Bearer PROGRESS_TOKEN required)
// Any KV error degrades to {active:false} so the panel simply hides — never a 500.
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.method === 'POST') {
      // Fail CLOSED: a missing PROGRESS_TOKEN means "auth not configured", not "any token works".
      // (Without this, `Bearer ${undefined}` matches the literal header "Bearer undefined".)
      const token = process.env.PROGRESS_TOKEN;
      const got = Buffer.from(req.headers.authorization || '');
      const want = Buffer.from(`Bearer ${token}`);
      if (!token || got.length !== want.length || !timingSafeEqual(got, want)) {
        res.status(401).json({ error: 'unauthorized' });
        return;
      }
      const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
      await kvClient().set('progress', body);
      res.status(200).json({ ok: true });
      return;
    }
    const data = (await kvClient().get('progress')) || { active: false };
    res.status(200).json(data);
  } catch {
    res.status(200).json({ active: false });
  }
}
