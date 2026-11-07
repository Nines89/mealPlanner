"""Optional development-only shortcut for a single local planner user."""
from threading import Lock

from django.conf import settings
from django.contrib.auth.models import User

from .slots import sync_lunch_dinner_slots
from .targets import ensure_on_off_targets

PLANNER_USERNAME = 'me'
_LOCAL_SETUP_DONE = False
_LOCAL_SETUP_LOCK = Lock()


def get_or_create_local_user():
    """Reuse the first existing account (keeps current data) or create ``me``."""
    existing = User.objects.order_by('id').first()
    if existing:
        return existing
    return User.objects.create_user(username=PLANNER_USERNAME)


class AutoLoginLocalUserMiddleware:
    """
    For the household app, anonymous requests run as the local planner user.
    ``/admin/`` is left anonymous so Django admin can still require a login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.LOCAL_AUTO_LOGIN or request.path.startswith('/admin/'):
            return self.get_response(request)
        if request.path.startswith('/static/') or request.path in {
            '/sw.js', '/manifest.webmanifest',
        }:
            return self.get_response(request)
        if not request.user.is_authenticated:
            # This convenience mode is deliberately opt-in: enabling it on a
            # reachable deployment would expose the first user's household.
            _ensure_local_setup()
            request.user = get_or_create_local_user()
        return self.get_response(request)


def _ensure_local_setup():
    global _LOCAL_SETUP_DONE
    if _LOCAL_SETUP_DONE:
        return
    with _LOCAL_SETUP_LOCK:
        if _LOCAL_SETUP_DONE:
            return
        sync_lunch_dinner_slots()
        ensure_on_off_targets()
        _LOCAL_SETUP_DONE = True
