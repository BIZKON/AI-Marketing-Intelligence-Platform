/**
 * Service Worker — handles push notifications, caching, and offline support.
 *
 * Cache strategies:
 *   - App shell (HTML, CSS, JS): cache-first, refresh in background
 *   - API calls: network-first, fall back to cache
 *   - Static assets (icons, images): cache-first
 */

const CACHE_NAME = "alchemya-v1";
const OFFLINE_URL = "/offline";

const APP_SHELL = [
  "/",
  "/training",
  "/dashboard",
  "/offline",
  "/icon-192.png",
  "/icon-512.png",
  "/manifest.json",
];

// ── Install ────────────────────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// ── Activate ───────────────────────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch ──────────────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") return;

  // API calls: network-first
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets: cache-first
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Pages: network-first with offline fallback
  event.respondWith(networkFirstWithOffline(request));
});

// ── Push Notifications ─────────────────────────────────────────────────────

self.addEventListener("push", (event) => {
  let data = { title: "Alchemya", body: "New notification", url: "/training" };

  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || "/icon-192.png",
    badge: data.badge || "/icon-192.png",
    vibrate: [100, 50, 100],
    data: { url: data.url || "/training" },
    actions: [
      { action: "open", title: "Open" },
      { action: "dismiss", title: "Dismiss" },
    ],
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  if (event.action === "dismiss") return;

  const url = event.notification.data?.url || "/training";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((c) => c.url.includes(url));
      if (existing) {
        return existing.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});

// ── Background Sync ────────────────────────────────────────────────────────

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-training-data") {
    event.waitUntil(syncTrainingData());
  }
});

async function syncTrainingData() {
  // Replay queued API calls when back online
  const cache = await caches.open("offline-queue");
  const requests = await cache.keys();

  for (const request of requests) {
    try {
      await fetch(request.clone());
      await cache.delete(request);
    } catch {
      // Still offline, will retry on next sync
      break;
    }
  }
}

// ── Cache Strategies ───────────────────────────────────────────────────────

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response("Offline", { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: "offline" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function networkFirstWithOffline(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Return offline page for navigation requests
    if (request.mode === "navigate") {
      const offlinePage = await caches.match(OFFLINE_URL);
      if (offlinePage) return offlinePage;
    }

    return new Response("Offline", { status: 503 });
  }
}

function isStaticAsset(pathname) {
  return /\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|eot)$/.test(pathname);
}
