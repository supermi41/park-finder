// Service Worker for 핀파인더 PWA — network-first for HTML to avoid stale shell lock-in
const VERSION = 'v11-simple-sgg-filter';
const CACHE = `parkfinder-${VERSION}`;

self.addEventListener('install', e => {
  // Activate immediately; don't precache shell (precaching is what locked users into stale HTML)
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(k => caches.delete(k)));
    await self.clients.claim();
    // Force open tabs to reload so they pick up the new HTML immediately
    const wins = await self.clients.matchAll({ type: 'window' });
    for (const c of wins) { try { await c.navigate(c.url); } catch (_) {} }
  })());
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // PMTiles & cross-origin: bypass SW entirely
  if (url.hostname !== self.location.hostname) return;
  if (url.pathname.endsWith('.pmtiles')) return;

  const accept = e.request.headers.get('accept') || '';
  const isHTML = url.pathname === '/' || url.pathname.endsWith('.html') || accept.includes('text/html');

  if (isHTML) {
    // network-first for HTML so users can never get stuck on old shell
    e.respondWith(
      fetch(e.request).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Everything else (JSON, manifest, icons): stale-while-revalidate
  e.respondWith(
    caches.match(e.request).then(cached => {
      const network = fetch(e.request).then(r => {
        if (r.ok && r.status === 200) {
          const copy = r.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return r;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
