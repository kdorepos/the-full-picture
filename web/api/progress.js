import { kv } from '@vercel/kv';

// Live transcription progress for the homepage "now processing" panel.
//   GET  → the last-pushed progress ({active:false} when idle or KV unset)
//   POST → the pipeline pushes an update (Bearer PROGRESS_TOKEN required)
// Any KV error degrades to {active:false} so the panel simply hides — never a 500.
export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.method === 'POST') {
      if (req.headers.authorization !== `Bearer ${process.env.PROGRESS_TOKEN}`) {
        res.status(401).json({ error: 'unauthorized' });
        return;
      }
      const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
      await kv.set('progress', body);
      res.status(200).json({ ok: true });
      return;
    }
    const data = (await kv.get('progress')) || { active: false };
    res.status(200).json(data);
  } catch {
    res.status(200).json({ active: false });
  }
}
