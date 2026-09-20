"""Optional development-only shortcut for a single local planner user."""
from django.conf import settings
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
        if not settings.LOCAL_AUTO_LOGIN or request.path.startswith('/admin/'):
            return self.get_response(request)
        if not request.user.is_authenticated:
            # This convenience mode is deliberately opt-in: enabling it on a
            # reachable deployment would expose the first user's household.
            sync_lunch_dinner_slots()
            ensure_on_off_targets()
            request.user = get_or_create_local_user()
        return self.get_response(request)
