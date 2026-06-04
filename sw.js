// Service Worker for 핀파인더 PWA
// Caches HTML shell + static JSON; PMTiles stay network (Range requests)
const VERSION = 'v1';
const CACHE = `parkfinder-${VERSION}`;
const SHELL = [
  '/',
  '/index.html',
  '/manifest.json',
  '/public/stats.json',
  '/public/districts.json',
  '/public/parcels-manifest.json',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Skip PMTiles & cross-origin (jsDelivr handles its own caching)
  if (url.hostname !== self.location.hostname) return;
  if (url.pathname.endsWith('.pmtiles')) return;
  // Cache-first for shell, network-first for parcels-N.json (may update)
  if (url.pathname.match(/parcels-\d+\.json$/)) {
    e.respondWith(
      fetch(e.request).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
      if (r.ok && r.status === 200) {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return r;
    }))
  );
});
