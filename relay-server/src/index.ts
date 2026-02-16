import { APP_HTML, MANIFEST_JSON, SW_JS, generateIconSvg } from "./pwa";

export interface Env {
  NOTIFICATIONS: KVNamespace;
  API_KEY: string;
}

interface Notification {
  id: string;
  pc_name: string;
  sender: string;
  channel: string;
  message: string;
  timestamp: string;
  status: "unread" | "read";
}

const MAX_PREVIEW_LENGTH = 80;
const EXPIRATION_TTL = 86400; // 24 hours

function truncate(s: string, maxLen: number): string {
  return s.length > maxLen ? s.slice(0, maxLen) + "…" : s;
}

function authenticate(request: Request, env: Env): Response | null {
  const auth = request.headers.get("Authorization");
  if (!auth || auth !== `Bearer ${env.API_KEY}`) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return null;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// POST /api/notifications — Agent sends a notification
async function handlePost(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    pc_name?: string;
    sender?: string;
    channel?: string;
    message?: string;
  }>();

  if (!body.pc_name || !body.message) {
    return jsonResponse({ error: "pc_name and message are required" }, 400);
  }

  const id = crypto.randomUUID();
  const timestamp = new Date().toISOString();
  const timestampMs = Date.now();

  const notification: Notification = {
    id,
    pc_name: body.pc_name,
    sender: body.sender || "",
    channel: body.channel || "",
    message: truncate(body.message, MAX_PREVIEW_LENGTH),
    timestamp,
    status: "unread",
  };

  const kvKey = `notif:${String(timestampMs).padStart(16, "0")}:${id}`;

  await Promise.all([
    env.NOTIFICATIONS.put(kvKey, JSON.stringify(notification), {
      expirationTtl: EXPIRATION_TTL,
    }),
    // Reverse index for PATCH lookup by UUID
    env.NOTIFICATIONS.put(`idx:${id}`, kvKey, {
      expirationTtl: EXPIRATION_TTL,
    }),
  ]);

  return jsonResponse({ id, timestamp }, 201);
}

// GET /api/notifications — Collector fetches notifications
async function handleGet(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const since = url.searchParams.get("since"); // ISO timestamp
  const status = url.searchParams.get("status"); // "unread" | "read"
  const pcName = url.searchParams.get("pc_name");

  // List all notification keys (KV list is prefix-based, sorted lexicographically)
  const listed = await env.NOTIFICATIONS.list({ prefix: "notif:" });

  const notifications: Notification[] = [];

  // Fetch values in parallel (batched)
  const keys = listed.keys.map((k) => k.name);
  const values = await Promise.all(keys.map((k) => env.NOTIFICATIONS.get(k)));

  for (const raw of values) {
    if (!raw) continue;
    const notif: Notification = JSON.parse(raw);

    // Apply filters
    if (since && notif.timestamp < since) continue;
    if (status && notif.status !== status) continue;
    if (pcName && notif.pc_name !== pcName) continue;

    notifications.push(notif);
  }

  // Sort by timestamp ascending
  notifications.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  return jsonResponse({ notifications });
}

// PATCH /api/notifications/:id — Mark as read
async function handlePatch(
  request: Request,
  env: Env,
  id: string
): Promise<Response> {
  // Look up the KV key via reverse index
  const kvKey = await env.NOTIFICATIONS.get(`idx:${id}`);
  if (!kvKey) {
    return jsonResponse({ error: "Not found" }, 404);
  }

  const raw = await env.NOTIFICATIONS.get(kvKey);
  if (!raw) {
    return jsonResponse({ error: "Not found" }, 404);
  }

  const notification: Notification = JSON.parse(raw);
  notification.status = "read";

  await env.NOTIFICATIONS.put(kvKey, JSON.stringify(notification), {
    expirationTtl: EXPIRATION_TTL,
  });

  return jsonResponse({ id, status: "read" });
}

// --- PWA static assets (no auth required) ---

function servePwa(path: string): Response | null {
  if (path === "/" || path === "/index.html") {
    return new Response(APP_HTML, {
      headers: { "Content-Type": "text/html;charset=utf-8" },
    });
  }
  if (path === "/manifest.json") {
    return new Response(MANIFEST_JSON, {
      headers: { "Content-Type": "application/manifest+json" },
    });
  }
  if (path === "/sw.js") {
    return new Response(SW_JS, {
      headers: { "Content-Type": "application/javascript" },
    });
  }
  if (path === "/icon-192.png" || path === "/icon-512.png") {
    const size = path.includes("192") ? 192 : 512;
    return new Response(generateIconSvg(size), {
      headers: { "Content-Type": "image/svg+xml" },
    });
  }
  return null;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // PWA static routes — no authentication
    const pwaResponse = servePwa(path);
    if (pwaResponse) return pwaResponse;

    // API routes — require authentication
    const authError = authenticate(request, env);
    if (authError) return authError;

    // POST /api/notifications
    if (request.method === "POST" && path === "/api/notifications") {
      return handlePost(request, env);
    }

    // GET /api/notifications
    if (request.method === "GET" && path === "/api/notifications") {
      return handleGet(request, env);
    }

    // PATCH /api/notifications/:id
    const patchMatch = path.match(/^\/api\/notifications\/([a-f0-9-]+)$/);
    if (request.method === "PATCH" && patchMatch) {
      return handlePatch(request, env, patchMatch[1]);
    }

    return jsonResponse({ error: "Not found" }, 404);
  },
};
