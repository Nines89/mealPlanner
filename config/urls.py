from django.contrib import admin
from django.urls import path, include

from core.pwa_views import service_worker, web_manifest

urlpatterns = [
    # PWA: percorsi root per scope SW e Content-Type corretto sul manifest
    path('manifest.webmanifest', web_manifest, name='pwa_manifest'),
    path('sw.js', service_worker, name='pwa_service_worker'),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/', include('core.api_urls')),
    path('', include('core.urls')),
]