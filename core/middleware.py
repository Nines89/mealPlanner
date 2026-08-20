"""Attach a single local planner user so the app needs no login screen."""
from django.contrib.auth.models import User

from .slots import sync_lunch_dinner_slots
from .targets import ensure_on_off_targets

PLANNER_USERNAME = 'me'


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
        if request.path.startswith('/admin/'):
            return self.get_response(request)
        sync_lunch_dinner_slots()
        ensure_on_off_targets()
        if not request.user.is_authenticated:
            request.user = get_or_create_local_user()
        return self.get_response(request)
