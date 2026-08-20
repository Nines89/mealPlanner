"""
PWA: manifest and service worker served from the origin root.

Why not only ``static/``?
- A service worker's default scope is the directory of the file. ``/static/sw.js``
  cannot control navigations to ``/``.
- ``/sw.js`` has scope ``/`` so we can intercept only what we choose (here: ``/static/``).
"""

import json
from pathlib import Path

from django.http import HttpResponse
from django.templatetags.static import static


def _sw_source_bytes() -> bytes:
    path = Path(__file__).resolve().parent / 'pwa' / 'sw.js'
    return path.read_bytes()


def service_worker(request):
    """Serve ``/sw.js`` with the MIME type browsers expect."""
    body = _sw_source_bytes()
    resp = HttpResponse(body, content_type='application/javascript; charset=utf-8')
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    return resp


def web_manifest(request):
    """
    ``/manifest.webmanifest`` — Web App Manifest (JSON).

    Absolute icon URLs: some browsers/Android are more tolerant of that.
    """
    icon_192 = request.build_absolute_uri(static('pwa/icon-192.png'))
    icon_512 = request.build_absolute_uri(static('pwa/icon-512.png'))
    app_id = request.build_absolute_uri('/')
    data = {
        'id': app_id,
        'name': 'Meal Planner',
        'short_name': 'Meal',
        'description': 'Meal plan and nutrition',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'background_color': '#f9fafb',
        'theme_color': '#059669',
        'lang': 'en',
        'icons': [
            {
                'src': icon_192,
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_512,
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_192,
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'maskable',
            },
            {
                'src': icon_512,
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
    }
    resp = HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type='application/manifest+json; charset=utf-8',
    )
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp
