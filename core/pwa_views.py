"""
PWA: manifest e service worker serviti dalla root dell'origine.

Perché non solo ``static/``?
- Lo scope di un SW è (di default) la directory del file. Un file in ``/static/sw.js``
  non controlla le navigazioni verso ``/`` o ``/accounts/…``.
- ``/sw.js`` ha scope ``/`` → possiamo intercettare solo ciò che decidiamo (qui: ``/static/``).
"""

import json
from pathlib import Path

from django.http import HttpResponse
from django.templatetags.static import static


def _sw_source_bytes() -> bytes:
    path = Path(__file__).resolve().parent / 'pwa' / 'sw.js'
    return path.read_bytes()


def service_worker(request):
    """Serve ``/sw.js`` con tipo MIME corretto per i browser."""
    body = _sw_source_bytes()
    resp = HttpResponse(body, content_type='application/javascript; charset=utf-8')
    # Evita caching aggressivo dello SW da parte di CDN/browser durante lo sviluppo
    resp.headers['Cache-Control'] = 'no-cache, max-age=0'
    return resp


def web_manifest(request):
    """
    ``/manifest.webmanifest`` — Web App Manifest (JSON).

    URL delle icone assoluti: alcuni browser/Android sono più tolleranti così.
    """
    icon_192 = request.build_absolute_uri(static('pwa/icon-192.png'))
    icon_512 = request.build_absolute_uri(static('pwa/icon-512.png'))
    data = {
        'name': 'Meal Planner',
        'short_name': 'Meal',
        'description': 'Piano pasti e nutrizione',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'background_color': '#f9fafb',
        'theme_color': '#059669',
        'lang': 'it',
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
