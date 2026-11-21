/* Suvacya PWA worker: cache only the public offline document and immutable static assets.
   Authenticated HTML, API responses, OAuth redirects and user data are never cached. */
const CACHE_NAME = 'suvacya-shell-v3';
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.add(OFFLINE_URL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith('suvacya-shell-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/') ||
      url.pathname.includes('linkedin') || url.pathname.startsWith('/_next/image')) return;

  if (request.mode === 'navigate') {
    // Always revalidate app pages against the server. Never persist authenticated HTML.
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match(OFFLINE_URL)) || Response.error();
      })
    );
    return;
  }

  // Cache only Next.js content-addressed assets and public app icons.
  const isImmutableAsset = url.pathname.startsWith('/_next/static/');
  const isPublicIcon = url.pathname.startsWith('/icons/');
  if (!isImmutableAsset && !isPublicIcon) return;

  event.respondWith(
    caches.match(request).then(async (cached) => {
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok && (response.type === 'basic' || response.type === 'cors')) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    })
  );
});
