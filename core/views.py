from datetime import date

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AddHouseholdMemberForm, FillSlotForm
from .models import DayKind, Household, MealSlot, WeekDay, WeekPlanSlot
from .nutrition import build_today_slots, expected_macros_for_day
from .planning import shopping_list_for_plan
from .targets import day_kind_map, get_target_by_kind
from .week import (
    apply_fill,
    assign_random_meals,
    get_current_week_plan,
    load_fill_page,
    monday_of_week,
    rescale_assigned_portions,
    save_day_kinds,
    save_genre_grid,
    week_plan_for_monday,
    week_plan_page_context,
)


def _household_context(user):
    household = Household.ensure_for_user(user)
    members = list(household.members.order_by('sort_order', 'id'))
    return household, members, len(members) or 1


def _slots_assigned_on(week_plan, day):
    return {
        slot.meal_slot_id: slot
        for slot in WeekPlanSlot.objects.filter(week_plan=week_plan, day=day)
        .select_related('meal')
        .prefetch_related('meal__meal_ingredients__ingredient')
    }


@require_http_methods(['GET', 'POST'])
def dashboard(request):
    user = request.user
    household, members, member_count = _household_context(user)
    today = date.today()
    week_plan, _monday = get_current_week_plan(user)
    day = today.weekday()
    kind = day_kind_map(week_plan).get(day) or DayKind.OFF
    day_target = get_target_by_kind(kind)
    meal_slots = list(MealSlot.objects.filter(user=user).order_by('order'))
    rescale_assigned_portions(week_plan, meal_slots)
    today_slots, day_effective = build_today_slots(
        meal_slots, _slots_assigned_on(week_plan, day), member_count
    )
    return render(
        request,
        'core/dashboard.html',
        {
            'household': household,
            'members': members,
            'member_count': member_count,
            'on_target': get_target_by_kind(DayKind.ON),
            'off_target': get_target_by_kind(DayKind.OFF),
            'today': today,
            'today_day': day,
            'today_label': WeekDay(day).label,
            'today_kind': kind,
            'day_target': day_target,
            'today_slots': today_slots,
            'day_effective': day_effective,
            'day_expected': expected_macros_for_day(day_target, member_count),
        },
    )


@require_http_methods(['GET', 'POST'])
def nutrition_target_edit(request):
    return redirect('core:dashboard')


@require_http_methods(['GET', 'POST'])
def week_plan_current(request):
    """Current ISO week: meal grid plus household expected vs effective totals."""
    week_plan, monday = get_current_week_plan(request.user)
    if request.method == 'POST':
        response = _handle_week_plan_post(request, week_plan)
        if response is not None:
            return response
    return render(
        request,
        'core/week_plan.html',
        week_plan_page_context(request.user, week_plan, monday),
    )


def _handle_week_plan_post(request, week_plan):
    handlers = {
        'day_kinds': _save_week_day_kinds,
        'meal_grid': _save_week_genre_grid,
        'build': _build_week_meals,
    }
    handler = handlers.get(request.POST.get('form_id'))
    if handler is None:
        return None
    return handler(request, week_plan)


def _save_week_day_kinds(request, week_plan):
    save_day_kinds(week_plan, request.POST)
    meal_slots = list(MealSlot.objects.filter(user=request.user).order_by('order'))
    rescale_assigned_portions(week_plan, meal_slots)
    messages.success(request, 'ON/OFF days saved.')
    return redirect('core:week_plan')


def _save_week_genre_grid(request, week_plan):
    meal_slots = list(MealSlot.objects.filter(user=request.user).order_by('order'))
    result = save_genre_grid(week_plan, meal_slots, request.POST)
    if result.invalid:
        messages.error(request, 'Some selected categories are not valid and were ignored.')
    messages.success(
        request,
        f'Week plan updated: {result.updated} cells saved, {result.removed} cells cleared.',
    )
    return redirect('core:week_plan')


def _build_week_meals(request, week_plan):
    meal_slots = list(MealSlot.objects.filter(user=request.user).order_by('order'))
    save_genre_grid(week_plan, meal_slots, request.POST)
    result = assign_random_meals(week_plan, meal_slots)
    if result.invalid:
        messages.warning(
            request,
            f'No catalog dish for {result.invalid} '
            f'{"category" if result.invalid == 1 else "categories"}.',
        )
    messages.success(request, f'Built week: {result.updated} dishes assigned.')
    return redirect('core:week_plan')


@require_http_methods(['GET', 'POST'])
def week_plan_fill_slot(request, day, slot_id):
    """Fill one week-plan cell with a scaled protein + vegetable plate."""
    if day not in range(7):
        raise Http404()
    meal_slot = get_object_or_404(MealSlot, id=slot_id, user=request.user)
    page = load_fill_page(request.user, day, meal_slot)
    if page is None:
        messages.error(request, 'ON/OFF targets are missing.')
        return redirect('core:dashboard')
    if request.method == 'POST':
        return _fill_slot_post(request, page)
    form = FillSlotForm(diet_style=page.diet_style)
    return render(request, 'core/week_plan_fill.html', page.template_context(form))


def _fill_slot_post(request, page):
    form = FillSlotForm(request.POST, diet_style=page.diet_style)
    if not form.is_valid():
        return render(request, 'core/week_plan_fill.html', page.template_context(form))
    meal = apply_fill(page, form.cleaned_data)
    if meal is None:
        messages.error(
            request,
            'Not enough ingredients in the catalog for this mode (need a protein and a vegetable).',
        )
        return render(request, 'core/week_plan_fill.html', page.template_context(form))
    messages.success(
        request,
        f'Filled {WeekDay(page.day).label} {page.meal_slot.name}: {meal.name}.',
    )
    return redirect('core:week_plan')


@require_http_methods(['GET', 'POST'])
def household_manage(request):
    """Add/remove household names (count is used for shopping and totals)."""
    household, members, _count = _household_context(request.user)
    if request.method == 'POST':
        _handle_household_post(request, household)
        return redirect('core:household')
    return render(
        request,
        'core/household.html',
        {
            'household': household,
            'members': members,
            'form': AddHouseholdMemberForm(),
        },
    )


def _handle_household_post(request, household):
    handlers = {
        'add': _household_add,
        'delete': _household_delete,
    }
    handler = handlers.get(request.POST.get('action'))
    if handler is not None:
        handler(request, household)


def _household_add(request, household):
    form = AddHouseholdMemberForm(request.POST)
    if not form.is_valid():
        return
    member = household.add_named_member(form.cleaned_data['display_name'])
    if member:
        messages.success(request, f'Added “{member.display_name}”.')


def _household_delete(request, household):
    try:
        member_id = int(request.POST.get('member_id'))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid request.')
        return
    outcome = household.try_remove_member(member_id)
    _REMOVE_MESSAGES[outcome](request)


def _message_member_removed(request):
    messages.success(request, 'Member removed.')


def _message_member_not_found(request):
    messages.error(request, 'Member not found.')


def _message_keep_one_member(request):
    messages.error(request, 'Keep at least one household member.')


_REMOVE_MESSAGES = {
    'removed': _message_member_removed,
    'not_found': _message_member_not_found,
    'last_member': _message_keep_one_member,
}


@require_http_methods(['GET'])
def shopping_list(request):
    """Weekly shopping list: plate grams × household size."""
    user = request.user
    monday = monday_of_week()
    household = Household.ensure_for_user(user)
    member_count = household.member_count() or 1
    week_plan = week_plan_for_monday(user, monday)
    rows = shopping_list_for_plan(week_plan, member_count) if week_plan else []
    return render(
        request,
        'core/shopping_list.html',
        {
            'week_start': monday,
            'week_plan': week_plan,
            'member_count': member_count,
            'rows': rows,
        },
    )
