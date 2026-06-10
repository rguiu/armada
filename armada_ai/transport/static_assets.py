"""Static asset routes: manifest, service worker, app icon."""
from fastapi.responses import JSONResponse, Response


def manifest_route():
    return JSONResponse({
        "name": "Armada Fleet Dashboard",
        "short_name": "Armada",
        "description": "Command your fleet of AI agents",
        "start_url": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0f1117",
        "theme_color": "#0f1117",
        "icons": [
            {"src": "/icon.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"},
        ],
    })


_SW_SCRIPT = """\
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => {
  caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))));
  e.waitUntil(clients.claim());
});"""


def service_worker_route():
    return Response(content=_SW_SCRIPT, media_type="application/javascript")


_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="92" fill="url(#bg)"/>
  <g transform="translate(256,256)" fill="none" stroke="#58a6ff" stroke-width="28" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="-40" cy="-60" r="32"/>
    <circle cx="40" cy="-60" r="32"/>
    <circle cx="0" cy="20" r="32"/>
    <line x1="-40" y1="-28" x2="0" y2="-12"/>
    <line x1="40" y1="-28" x2="0" y2="-12"/>
    <line x1="0" y1="52" x2="0" y2="160"/>
    <line x1="-80" y1="160" x2="80" y2="160"/>
    <path d="M-160,200 Q0,260 160,200" stroke-width="22"/>
  </g>
</svg>"""


def app_icon_route():
    return Response(content=_ICON_SVG, media_type="image/svg+xml")
