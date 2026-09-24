from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.pwa_views import service_worker, web_manifest

urlpatterns = [
    # PWA: root paths so the SW scope covers the app and the manifest has the right Content-Type.
    path('manifest.webmanifest', web_manifest, name='pwa_manifest'),
    path('sw.js', service_worker, name='pwa_service_worker'),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('api/', include('core.api_urls')),
    path('', include('core.urls')),
]
