from datetime import date, timedelta
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import AddHouseholdMemberForm, FillSlotForm
from .models import (
    DayKind,
    Household,
    Ingredient,
    MealSlot,
    ShoppingListHiddenIngredient,
    ShoppingListIngredientOverride,
    ShoppingListManualItem,
    ShoppingListOrder,
    WeekDay,
    WeekPlanSlot,
)
from .nutrition import build_today_slots, expected_macros_for_day
from .planning import shopping_list_for_plan
from .targets import targets_for_week_plan
from .week import (
    apply_fill,
    assign_random_meals,
    clear_week_plan_meals,
    get_current_week_plan,
    get_week_plan,
    load_fill_page,
    monday_of_week,
    rebuild_slot_meal,
    rescale_assigned_portions,
    replace_week_plan_vegetable,
    save_day_kinds,
    save_genre_grid,
    week_plan_for_monday,
    week_plan_page_context, swap_slots,
)

SHOPPING_LIST_SECTIONS = (
    'Carboidrati',
    'Proteine e latticini',
    'Grassi e altri',
    'Vegetali',
)
SHOPPING_LIST_UNIT_LABELS = {
    'g': ('g', 'g'),
    'kg': ('kg', 'kg'),
    'ml': ('ml', 'ml'),
    'l': ('l', 'l'),
    'pz': ('pezzo', 'pezzi'),
    'confezione': ('confezione', 'confezioni'),
}


def _household_context(user):
    household = Household.ensure_for_user(user)
    members = list(household.members.order_by('sort_order', 'id'))
    return household, members, len(members) or 1


def _slots_assigned_on(week_plan, day):
    return {
        slot.meal_slot_id: slot # noqa
        for slot in WeekPlanSlot.objects.filter(week_plan=week_plan, day=day)
        .select_related('meal')
        .prefetch_related('meal__meal_ingredients__ingredient')
    }


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    user = request.user
    household, members, member_count = _household_context(user)
    today = date.today()
    week_plan, _monday = get_current_week_plan(user)
    day = today.weekday()
    targets_by_kind, day_targets = targets_for_week_plan(week_plan)
    day_target = day_targets.get(day)
    kind = day_target.kind if day_target else DayKind.OFF
    meal_slots = list(MealSlot.objects.filter(user=user).order_by('order'))
    rescale_assigned_portions(week_plan, meal_slots, day_targets)
    today_slots, day_effective = build_today_slots(
        meal_slots, _slots_assigned_on(week_plan, day), member_count
    )
    assigned_today = _slots_assigned_on(week_plan, day)
    skipped_today = [
        meal_slot for meal_slot in meal_slots
        if (plan_slot := assigned_today.get(meal_slot.id)) and plan_slot.skipped # noqa
    ]
    return render(
        request,
        'core/dashboard.html',
        {
            'household': household,
            'members': members,
            'member_count': member_count,
            'on_target': targets_by_kind.get(DayKind.ON),
            'off_target': targets_by_kind.get(DayKind.OFF),
            'today': today,
            'today_day': day,
            'today_label': WeekDay(day).label,
            'today_kind': kind,
            'day_target': day_target,
            'today_slots': today_slots,
            'day_effective': day_effective,
            'day_expected': expected_macros_for_day(
                day_target, member_count,
                skipped_meal_slots=skipped_today, all_slots=meal_slots,
            ),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def nutrition_target_edit(request): # noqa
    return redirect('core:dashboard')


@login_required
@require_http_methods(['GET', 'POST'])
def week_plan_current(request):
    """Requested ISO week: meal grid plus household expected vs effective totals."""
    monday = _requested_week_start(request)
    week_plan, _monday = get_week_plan(request.user, monday)
    if request.method == 'POST':
        response = _handle_week_plan_post(request, week_plan)
        if response is not None:
            return response
    return render(
        request,
        'core/week_plan.html',
        week_plan_page_context(request.user, week_plan, monday),
    )


def _requested_week_start(request):
    raw_week = request.GET.get('week')
    if not raw_week:
        return monday_of_week()
    try:
        requested = date.fromisoformat(raw_week)
    except ValueError as exc:
        raise Http404('Invalid week.') from exc
    if requested.weekday() != 0:
        raise Http404('Week must start on a Monday.')
    return requested


def _week_plan_redirect(request):
    """Preserve the selected week after a save/build/rebuild POST."""
    return redirect(request.get_full_path())


def _handle_week_plan_post(request, week_plan):
    handlers = {
        'day_kinds': _save_week_day_kinds,
        'meal_grid': _save_week_genre_grid,
        'build': _build_week_meals,
        'clear': _clear_week_meals,
        'replace_vegetable': _replace_week_vegetable,
        'rebuild_slot': _rebuild_week_slot,
        'swap_slots': _swap_week_slots,
    }
    handler = handlers.get(request.POST.get('form_id'))
    if handler is None:
        return None
    return handler(request, week_plan)


def _planner_meal_slots(user):
    return list(MealSlot.objects.filter(user=user).order_by('order'))


def _save_posted_genre_grid(week_plan, meal_slots, post_data):
    if not any(key.startswith('genre_') for key in post_data):
        return None
    return save_genre_grid(week_plan, meal_slots, post_data)


def _save_posted_day_kinds(week_plan, post_data):
    if 'day_kind_0' not in post_data:
        return
    save_day_kinds(week_plan, post_data)


def _save_week_day_kinds(request, week_plan):
    meal_slots = _planner_meal_slots(request.user)
    _save_posted_genre_grid(week_plan, meal_slots, request.POST)
    save_day_kinds(week_plan, request.POST)
    rescale_assigned_portions(week_plan, meal_slots)
    messages.success(request, 'ON/OFF days saved.')
    return _week_plan_redirect(request)


def _save_week_genre_grid(request, week_plan):
    meal_slots = _planner_meal_slots(request.user)
    _save_posted_day_kinds(week_plan, request.POST)
    result = save_genre_grid(week_plan, meal_slots, request.POST)
    if result.invalid:
        messages.error(request, 'Some selected categories are not valid and were ignored.')
    messages.success(
        request,
        f'Week plan updated: {result.updated} cells saved, {result.removed} cells cleared.',
    )
    return _week_plan_redirect(request)


def _build_week_meals(request, week_plan):
    meal_slots = _planner_meal_slots(request.user)
    _save_posted_day_kinds(week_plan, request.POST)
    save_genre_grid(week_plan, meal_slots, request.POST)
    result = assign_random_meals(week_plan, meal_slots)
    if result.invalid:
        messages.warning(
            request,
            f'No catalog dish for {result.invalid} '
            f'{"category" if result.invalid == 1 else "categories"}.',
        )
    if result.updated:
        messages.success(
            request,
            f'Assigned {result.updated} new '
            f'{"dish" if result.updated == 1 else "dishes"}. Existing meals were kept.',
        )
    elif not result.invalid:
        messages.info(request, 'No empty slots to fill. Existing dishes were kept.')
    return _week_plan_redirect(request)


def _clear_week_meals(request, week_plan):
    removed = clear_week_plan_meals(week_plan)
    messages.success(request, f'Cleared {removed} recipes from this week.')
    return _week_plan_redirect(request)


def _replace_week_vegetable(request, week_plan):
    try:
        day = int(request.POST.get('vegetable_day', ''))
        meal_slot_id = int(request.POST.get('vegetable_slot_id', ''))
        old_ingredient_id = int(request.POST.get('vegetable_old_id', ''))
        new_ingredient_id = int(request.POST.get('vegetable_new_id', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Could not update the recipe vegetables.')
        return _week_plan_redirect(request)

    if replace_week_plan_vegetable(
        week_plan, day, meal_slot_id, old_ingredient_id, new_ingredient_id
    ):
        messages.success(request, 'Recipe vegetable updated for this week.')
    else:
        messages.error(request, 'That vegetable could not be changed for this recipe.')
    return _week_plan_redirect(request)


def _posted_slot_ref(post_data):
    try:
        day = int(post_data.get('rebuild_day', ''))
        slot_id = int(post_data.get('rebuild_slot_id', ''))
    except (TypeError, ValueError):
        return None, None
    if day not in range(7):
        return None, None
    return day, slot_id


def _rebuild_week_slot(request, week_plan):
    meal_slots = _planner_meal_slots(request.user)
    _save_posted_day_kinds(week_plan, request.POST)
    save_genre_grid(week_plan, meal_slots, request.POST)
    day, slot_id = _posted_slot_ref(request.POST)
    meal_slot = next((slot for slot in meal_slots if slot.id == slot_id), None) # noqa
    if day is None or meal_slot is None:
        messages.error(request, 'That meal slot could not be rebuilt.')
        return _week_plan_redirect(request)
    result = rebuild_slot_meal(week_plan, meal_slots, day, meal_slot)
    _notify_slot_rebuild(request, result)
    return _week_plan_redirect(request)


def _notify_slot_rebuild(request, result):
    if result.missing:
        messages.warning(request, 'No catalog dish for this category.')
        return
    if result.dish_name and result.dish_name != result.previous_name:
        messages.success(request, f'Switched to {result.dish_name}.')
        return
    messages.info(request, 'No other dish in this category.')


@login_required
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


@login_required
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


@login_required
@require_http_methods(['GET'])
def shopping_list(request):
    """Selected week's shopping list: plate grams × household size."""
    user = request.user
    monday = _requested_week_start(request)
    household = Household.ensure_for_user(user)
    member_count = household.member_count() or 1
    week_plan = week_plan_for_monday(user, monday)
    rows = _shopping_list_rows(user, monday, week_plan, member_count)
    saved_order = ShoppingListOrder.objects.filter(
        owner=user, week_start=monday
    ).values_list('items', flat=True).first()
    if saved_order:
        rows = _apply_shopping_list_order(rows, saved_order)
    return render(
        request,
        'core/shopping_list.html',
        {
            'week_start': monday,
            'previous_week_start': monday - timedelta(days=7),
            'next_week_start': monday + timedelta(days=7),
            'week_plan': week_plan,
            'member_count': member_count,
            'rows': rows,
        },
    )


@login_required
@require_POST
def move_shopping_list_to_alexa(request: HttpRequest) -> HttpResponseRedirect:
    try:
        monday = date.fromisoformat(request.POST.get('week', ''))
    except ValueError as exc:
        raise Http404('Invalid week.') from exc
    if monday.weekday() != 0:
        raise Http404('Week must start on a Monday.')

    week_plan = week_plan_for_monday(request.user, monday)
    household = Household.ensure_for_user(request.user)
    rows = _shopping_list_rows(
        request.user, monday, week_plan, household.member_count() or 1
    )
    if not rows:
        messages.warning(request, 'La lista della spesa è vuota.')
        return redirect(f"/lista-spesa/?week={monday.isoformat()}")

    items = []
    for row in rows:
        name = str(row['name']).strip()
        grams = row.get('grams')
        if grams is not None:
            weight = f"{format(grams.normalize(), 'f')}g"
        else:
            weight = ''.join(str(row.get('quantity') or '').split())
        items.append(f'{name}: {weight}')

    try:
        from .amazon_alexa import main as send_items_to_alexa

        send_items_to_alexa(items)
    except Exception as exc:
        messages.error(request, f'Invio ad Alexa non riuscito: {exc}')
    else:
        messages.success(request, f'{len(items)} elementi inviati alla lista Alexa.')

    return redirect(f"/lista-spesa/?week={monday.isoformat()}")


@login_required
@require_POST
def save_shopping_list_order(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body)
        week_start = date.fromisoformat(payload['week'])
        items = payload['items']
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid shopping list order.'}, status=400)
    if week_start.weekday() != 0 or not isinstance(items, list):
        return JsonResponse({'error': 'Invalid shopping list order.'}, status=400)

    week_plan = week_plan_for_monday(request.user, week_start)
    household = Household.ensure_for_user(request.user)
    current_rows = _shopping_list_rows(
        request.user, week_start, week_plan, household.member_count() or 1
    )
    valid_ids = {row['order_id'] for row in current_rows}
    saved_items = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get('id')
        section = item.get('section')
        if (
            not isinstance(item_id, str)
            or item_id not in valid_ids
            or item_id in seen
            or section not in SHOPPING_LIST_SECTIONS
        ):
            continue
        seen.add(item_id)
        saved_items.append({'id': item_id, 'section': section})

    ShoppingListOrder.objects.update_or_create(
        owner=request.user,
        week_start=week_start,
        defaults={'items': saved_items},
    )
    return JsonResponse({'saved': True})


def _apply_shopping_list_order(rows: list[dict], saved_items: list[dict]) -> list[dict]:
    by_id = {row['order_id']: row for row in rows}
    grouped = {section: [] for section in SHOPPING_LIST_SECTIONS}
    seen = set()
    for item in saved_items:
        if not isinstance(item, dict):
            continue
        row = by_id.get(str(item.get('id')))
        section = item.get('section')
        if row is None or section not in grouped or row['order_id'] in seen:
            continue
        row['section'] = section
        grouped[section].append(row)
        seen.add(row['order_id'])
    for row in rows:
        if row['order_id'] not in seen:
            grouped[row['section']].append(row)
    return [row for section in SHOPPING_LIST_SECTIONS for row in grouped[section]]


def _shopping_list_rows(user, monday, week_plan, member_count):
    rows = shopping_list_for_plan(week_plan, member_count) if week_plan else []
    hidden_ids = set(ShoppingListHiddenIngredient.objects.filter(
        owner=user, week_start=monday
    ).values_list('ingredient_id', flat=True))
    rows = [row for row in rows if row['ingredient_id'] not in hidden_ids]
    overrides = {
        row.ingredient_id: row
        for row in ShoppingListIngredientOverride.objects.filter(
            owner=user, week_start=monday
        )
    }
    for row in rows:
        override = overrides.get(row['ingredient_id'])
        if override:
            row['name'] = override.name or row['name']
            row['quantity'] = override.quantity or row['quantity']
        row['edit_quantity'] = row['quantity']
    manual_items = ShoppingListManualItem.objects.filter(
        owner=user, week_start=monday
    )
    for item in manual_items:
        rows.append({
            'order_id': f'manual-{item.id}',
            'manual_id': item.id,
            'name': item.name,
            'quantity': item.quantity or '—',
            'edit_quantity': item.quantity,
            'section': item.section,
            'manual': True,
        })
    return rows


@login_required
@require_http_methods(['GET', 'POST'])
def edit_shopping_list_item(
    request: HttpRequest, item_key: str
) -> HttpResponseRedirect | HttpResponse:
    raw_week = request.GET.get('week') if request.method == 'GET' else request.POST.get('week')
    try:
        week_start = date.fromisoformat(raw_week or '')
    except ValueError:
        raise Http404('Invalid week.')
    if week_start.weekday() != 0:
        raise Http404('Week must start on a Monday.')
    week_plan = week_plan_for_monday(request.user, week_start)
    household = Household.ensure_for_user(request.user)
    rows = _shopping_list_rows(
        request.user, week_start, week_plan, household.member_count() or 1
    )
    row = next((item for item in rows if item['order_id'] == item_key), None)
    if row is None:
        raise Http404('Shopping list item not found.')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        quantity = request.POST.get('quantity', '').strip()
        if not name or len(name) > 100 or len(quantity) > 40:
            messages.error(request, 'Nome e quantità devono essere validi.')
        elif row.get('manual'):
            manual = get_object_or_404(
                ShoppingListManualItem,
                id=row['manual_id'], owner=request.user, week_start=week_start,
            )
            manual.name = name
            manual.quantity = quantity
            manual.save(update_fields=['name', 'quantity'])
            return redirect(f"/lista-spesa/?week={week_start.isoformat()}")
        else:
            override, _created = ShoppingListIngredientOverride.objects.get_or_create(
                owner=request.user,
                week_start=week_start,
                ingredient_id=row['ingredient_id'],
            )
            override.name = name
            override.quantity = quantity
            override.save(update_fields=['name', 'quantity'])
            return redirect(f"/lista-spesa/?week={week_start.isoformat()}")

    return render(
        request,
        'core/shopping_list_item_edit.html',
        {'row': row, 'week_start': week_start},
    )


@login_required
@require_POST
def add_shopping_list_item(request: HttpRequest) -> HttpResponseRedirect:
    name = request.POST.get('name', '').strip()
    raw_quantity = request.POST.get('quantity_value', '').strip()
    unit = request.POST.get('quantity_unit', '')
    section = request.POST.get('section', '')
    try:
        week_start = date.fromisoformat(request.POST.get('week', ''))
    except ValueError:
        raise Http404('Invalid week.')
    if week_start.weekday() != 0:
        raise Http404('Week must start on a Monday.')
    quantity = ''
    if raw_quantity:
        try:
            amount = Decimal(raw_quantity)
        except InvalidOperation:
            amount = Decimal('0')
        if (
            not amount.is_finite()
            or amount <= 0
            or amount > Decimal('99999999.99')
            or unit not in SHOPPING_LIST_UNIT_LABELS
        ):
            messages.error(request, 'Inserisci una quantità positiva e un’unità valida.')
            return redirect(f"/lista-spesa/?week={week_start.isoformat()}")
        amount_text = format(amount.normalize(), 'f')
        if '.' in amount_text:
            amount_text = amount_text.rstrip('0').rstrip('.')
        unit_label = SHOPPING_LIST_UNIT_LABELS[unit][amount != Decimal('1')]
        quantity = f'{amount_text.replace(".", ",")} {unit_label}'
    if not name or len(name) > 100 or section not in SHOPPING_LIST_SECTIONS:
        messages.error(request, 'Inserisci un nome valido, una quantità breve e una sezione.')
        return redirect(f"/lista-spesa/?week={week_start.isoformat()}")
    ShoppingListManualItem.objects.create(
        owner=request.user,
        week_start=week_start,
        name=name,
        quantity=quantity,
        section=section,
    )
    return redirect(f"/lista-spesa/?week={week_start.isoformat()}")


@login_required
@require_POST
def remove_shopping_list_item(
    request: HttpRequest, item_key: str
) -> HttpResponseRedirect:
    try:
        week_start = date.fromisoformat(request.POST.get('week', ''))
    except ValueError:
        raise Http404('Invalid week.')
    if week_start.weekday() != 0:
        raise Http404('Week must start on a Monday.')
    if item_key.startswith('manual-'):
        try:
            manual_id = int(item_key.removeprefix('manual-'))
        except ValueError:
            raise Http404('Invalid shopping list item.')
        ShoppingListManualItem.objects.filter(
            id=manual_id, owner=request.user, week_start=week_start
        ).delete()
    else:
        try:
            ingredient_id = int(item_key)
        except ValueError:
            raise Http404('Invalid shopping list item.')
        week_plan = week_plan_for_monday(request.user, week_start)
        if week_plan is not None:
            household = Household.ensure_for_user(request.user)
            valid_ids = {
                row['ingredient_id']
                for row in shopping_list_for_plan(week_plan, household.member_count() or 1)
            }
            if ingredient_id in valid_ids and Ingredient.objects.filter(pk=ingredient_id).exists():
                ShoppingListHiddenIngredient.objects.get_or_create(
                    owner=request.user,
                    week_start=week_start,
                    ingredient_id=ingredient_id,
                )
    return redirect(f"/lista-spesa/?week={week_start.isoformat()}")

def _posted_ref(post_data, day_key, slot_key):
    try:
        day = int(post_data.get(day_key, ''))
        slot_id = int(post_data.get(slot_key, ''))
    except (TypeError, ValueError):
        return None, None
    return (day, slot_id) if day in range(7) else (None, None)


def _swap_week_slots(request, week_plan):
    meal_slots = _planner_meal_slots(request.user)
    _save_posted_day_kinds(week_plan, request.POST)
    save_genre_grid(week_plan, meal_slots, request.POST)
    by_id = {slot.id: slot for slot in meal_slots}
    day_a, id_a = _posted_ref(request.POST, 'swap_from_day', 'swap_from_slot_id')
    day_b, id_b = _posted_ref(request.POST, 'swap_to_day', 'swap_to_slot_id')
    if day_a is None or day_b is None or id_a not in by_id or id_b not in by_id:
        messages.error(request, 'Those slots could not be swapped.')
    elif swap_slots(week_plan, day_a, by_id[id_a], day_b, by_id[id_b]):
        messages.success(request, 'Meals swapped.')
    return _week_plan_redirect(request)
