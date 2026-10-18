// Load test: 20 virtual users for 60 s, each walking a realistic onboarding journey.
// Measures the chat/API p95 (target < 3 s). Accounts are created in setup() through
// Supabase Auth so the run exercises real token verification.
//
//   make load    (BASE_URL, SUPABASE_URL, SUPABASE_ANON_KEY from .env)
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const SUPABASE = __ENV.SUPABASE_URL;
const ANON = __ENV.SUPABASE_ANON_KEY;
const VUS = Number(__ENV.VUS || 20);

const chat = new Trend('chat_reply_ms', true);
const api = new Trend('api_ms', true);

export const options = {
  scenarios: {
    journey: { executor: 'constant-vus', vus: VUS, duration: __ENV.DURATION || '60s' },
  },
  thresholds: {
    'http_req_duration{kind:api}': ['p(95)<3000'],
    chat_reply_ms: ['p(95)<3000'],
    // ISSUE-002 regression check — found by this k6 run: 1 in 500 requests failed before
    // reaching the app (uvicorn's 5 s keep-alive; fixed in the Dockerfile).
    http_req_failed: ['rate<0.01'],
  },
  setupTimeout: '120s',
};

const MESSAGES = [
  "it's mostly anxiety, about three months now",
  'How much does this cost?',
  "I'm a bit overwhelmed by all of this",
  'video works better for me',
  'Can I talk to a real person?',
];

export function setup() {
  const tokens = [];
  for (let i = 0; i < VUS; i++) {
    const email = `k6-${Date.now()}-${i}@riverside.test`;
    const res = http.post(
      `${SUPABASE}/auth/v1/signup`,
      JSON.stringify({ email, password: `k6-password-${i}-${Date.now()}` }),
      { headers: { apikey: ANON, 'Content-Type': 'application/json' } },
    );
    check(res, { 'signup ok': (r) => r.status === 200 });
    tokens.push(res.json('access_token'));
  }
  return { tokens };
}

function call(method, path, token, body, tag) {
  const params = {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    tags: { kind: 'api', name: tag || path },
  };
  const res = http.request(method, `${BASE}${path}`, body ? JSON.stringify(body) : null, params);
  api.add(res.timings.duration);
  return res;
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  call('GET', '/api/me', token);
  call('POST', '/api/consent', token, { onboarding: true, id_scan: false, age_confirmed: true });
  for (const text of MESSAGES) {
    const res = call('POST', '/api/intake/messages', token, { text }, 'intake_message');
    chat.add(res.timings.duration);
    check(res, { 'chat 200': (r) => r.status === 200 });
    sleep(2 + Math.random() * 3); // people read and type
  }
  call('GET', '/api/intake', token);
  sleep(1);
}
