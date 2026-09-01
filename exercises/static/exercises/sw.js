/* KettleBell Pro Service Worker */
const CACHE_NAME = 'kb-pages-v4';
const STATIC_CACHE = 'kb-static-v4';

/* Core assets to pre-cache on install */
const PRECACHE_URLS = [
  '/static/exercises/css/styles.css',
  '/static/exercises/js/favorites.js',
  '/static/exercises/img/favicon.svg',
  '/static/exercises/img/hero-kettlebell.png',
];

/* Only these anonymous documents may be persisted offline. Never cache a
 * dashboard, profile, plan, session, login response, or API response. */
const PUBLIC_DOCUMENT_PATHS = new Set([
  '/',
  '/exercises/',
  '/categories/',
  '/levels/',
]);

function offlineResponse() {
  return new Response(
    '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sin conexión · KettleBell Pro</title><body style="font-family:system-ui;padding:2rem;background:#0f172a;color:#e2e8f0"><h1>Sin conexión</h1><p>Vuelve a conectarte para abrir tu panel o guardar una sesión. Tu progreso local no se ha enviado todavía.</p></body></html>',
    { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 }
  );
}

/* ---- Install: pre-cache core assets ---- */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

/* ---- Activate: clean old caches ---- */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== STATIC_CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

/* ---- Fetch strategies ---- */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  /* Skip non-GET and cross-origin requests (except Google Fonts) */
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin && !url.hostname.includes('fonts.googleapis.com') && !url.hostname.includes('fonts.gstatic.com')) return;

  /* Static assets: cache-first */
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  /* Public HTML pages: network-first with cache fallback. */
  if (request.headers.get('accept')?.includes('text/html')) {
    if (!PUBLIC_DOCUMENT_PATHS.has(url.pathname)) {
      event.respondWith(fetch(request).catch(() => offlineResponse()));
      return;
    }
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok && response.headers.get('X-KB-Public-Cache') === '1') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) =>
            cached || caches.match('/') || offlineResponse()
          )
        )
    );
    return;
  }

  /* APIs and all non-static requests are network-only. A failed API call must
   * reach the page so the client can keep its pending draft/idempotency key. */
  event.respondWith(fetch(request));
});

/* ---- Push Notifications ---- */
self.addEventListener('push', (event) => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body || '',
    icon: '/static/exercises/img/icon-192.png',
    badge: '/static/exercises/img/favicon.svg',
    vibrate: [100, 50, 100],
    data: { url: data.url || '/' },
    actions: [
      { action: 'open', title: 'Abrir' },
      { action: 'dismiss', title: 'Cerrar' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'KettleBell Pro', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      /* Focus existing window if open */
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      /* Otherwise open new window */
      return clients.openWindow(targetUrl);
    })
  );
});
