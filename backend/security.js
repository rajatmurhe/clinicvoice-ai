const crypto = require('node:crypto');
const origins = () => (process.env.CLINICVOICE_ALLOWED_ORIGINS || 'http://localhost:5050,http://127.0.0.1:5050,http://localhost:5173,http://127.0.0.1:5173').split(',').map(s => s.trim());
const equal = (a, b) => typeof a === 'string' && typeof b === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
const serviceKey = () => process.env.CLINICVOICE_SERVICE_KEY || '';
const serviceAuthorized = req => serviceKey().length >= 32 && equal(req.headers.authorization, 'Bearer ' + serviceKey());
const signingKey = crypto.randomBytes(32);
const buckets = new Map();
function consume(key, maximum, windowMs) {
  const now = Date.now();
  // Bound memory even when clients rotate identities.
  if (buckets.size > 10000) for (const [k, v] of buckets) if (v.until <= now) buckets.delete(k);
  let b = buckets.get(key);
  if (!b || b.until <= now) {
    if (buckets.size >= 20000) return false;
    b = {until: now + windowMs, count: 0}; buckets.set(key, b);
  }
  return ++b.count <= maximum;
}
function sign(payload) { return crypto.createHmac('sha256', signingKey).update(payload).digest('hex'); }
function issueSession(req, res) {
  if (serviceKey().length < 32) return res.status(503).json({error: 'Demo service is not configured.'});
  if (!origins().includes(req.headers.origin)) return res.status(403).json({error: 'Origin not allowed.'});
  if (!consume('issue:' + req.ip, 10, 60000) || !consume('issue:global', 100, 60000)) return res.status(429).json({error: 'Please wait before starting another session.'});
  const payload = Buffer.from(JSON.stringify({id: crypto.randomUUID(), expires: Date.now() + 15 * 60000})).toString('base64url');
  res.set('Cache-Control', 'no-store').json({token: payload + '.' + sign(payload)});
}
function authorize(req, res, next) {
  if (serviceAuthorized(req)) return next();
  try {
    const raw = (req.headers.authorization || '').replace(/^Bearer /, '');
    const [payload, signature, extra] = raw.split('.');
    if (!payload || extra || !equal(signature, sign(payload))) throw new Error();
    const session = JSON.parse(Buffer.from(payload, 'base64url').toString());
    if (!session.id || session.expires <= Date.now()) throw new Error();
    if (!consume('session:' + session.id, 120, 15 * 60000)) return res.status(429).json({error: 'Demo session limit reached. Please try later.'});
    req.demoSession = session.id;
    next();
  } catch { res.status(401).json({error: 'Start a demo session first.'}); }
}
function serviceOnly(req, res, next) {
  if (!serviceAuthorized(req)) return res.status(401).json({error: 'Service authentication required.'});
  next();
}
function budget(req, res, next) {
  // Applies to anonymous demo and internal provider requests. Per-process cap;
  // provider-side limits remain necessary across replicas and restarts.
  const cap = Number(process.env.CLINICVOICE_REQUESTS_PER_HOUR || 300);
  if (!Number.isFinite(cap) || cap < 1 || !consume('paid:global', cap, 3600000)) return res.status(429).json({error: 'Demo request budget reached. Please try later.'});
  next();
}
function requestId(value) { return typeof value === 'string' && /^[A-Za-z0-9-]{1,64}$/.test(value) ? value : crypto.randomUUID(); }
module.exports = {origins, issueSession, authorize, serviceOnly, budget, requestId};
