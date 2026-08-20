from django.contrib import admin
from django.urls import path, include

from core.pwa_views import service_worker, web_manifest

urlpatterns = [
    # PWA: root paths so the SW scope covers the app and the manifest has the right Content-Type.
    path('manifest.webmanifest', web_manifest, name='pwa_manifest'),
    path('sw.js', service_worker, name='pwa_service_worker'),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]