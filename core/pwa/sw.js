/**
 * Service Worker — Meal Planner
 *
 * Strategia (sicura con sessioni Django):
 * - install/activate: aggiorna versione cache solo per asset statici.
 * - fetch: cache-first solo per URL che iniziano con /static/ (CSS/JS/img del progetto).
 * - Tutto il resto (HTML, HTMX, API, admin): sempre rete → niente HTML utente in cache SW.
 *
 * Chrome richiede un listener su "fetch" per i criteri di installabilità PWA.
 */
const STATIC_CACHE = 'mealplanner-static-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== STATIC_CACHE) {
            return caches.delete(key);
          }
          return Promise.resolve();
        }),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') {
    return;
  }
  try {
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
      return;
    }
    if (url.pathname.startsWith('/static/')) {
      event.respondWith(
        caches.open(STATIC_CACHE).then((cache) =>
          cache.match(request).then((cached) => {
            if (cached) {
              return cached;
            }
            return fetch(request).then((response) => {
              if (response && response.status === 200 && response.type === 'basic') {
                cache.put(request, response.clone());
              }
              return response;
            });
          }),
        ),
      );
    }
  } catch {
    /* ignore */
  }
});
