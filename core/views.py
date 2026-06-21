from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count, Max
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from .nutrition import compute_week_totals

from .models import (
    DayProfile,
    Household,
    HouseholdMember,
    Ingredient,
    Meal,
    MealSlot,
    NutritionTarget,
    WeekDay,
    WeekPlan,
    WeekPlanDayKind,
    WeekPlanSlot,
    WeekPlanSlotAttendance, DayProfileMemberModifier,
)


class AddHouseholdMemberForm(forms.Form):
    display_name = forms.CharField(
        max_length=80,
        label='Nome commensale',
        widget=forms.TextInput(attrs={'class': 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'}),
    )


class AddDayProfileForm(forms.Form):
    _w = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'
    name = forms.CharField(max_length=50, label='Nome tipo', widget=forms.TextInput(attrs={'class': _w}))
    notes = forms.CharField(
        required=False,
        label='Note (opzionali)',
        widget=forms.Textarea(attrs={'class': _w, 'rows': 2}),
    )


_NUTRITION_TARGET_WIDGET_CLASS = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'


class NutritionTargetCreateForm(forms.ModelForm):
    """Creazione target personale da pagina dedicata (owner impostato in vista)."""

    assign_to_member = forms.ModelChoiceField(
        queryset=HouseholdMember.objects.none(),
        required=False,
        label='Collega a commensale (opzionale)',
        widget=forms.Select(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
        help_text='Più persone possono condividere lo stesso target; qui imposti solo il collegamento iniziale.',
    )

    class Meta:
        model = NutritionTarget
        fields = (
            'name',
            'target_kcal',
            'target_protein',
            'target_carbs',
            'target_fat',
            'diet_style',
        )
        widgets = {
            'name': forms.TextInput(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
            'target_kcal': forms.NumberInput(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
            'target_protein': forms.NumberInput(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
            'target_carbs': forms.NumberInput(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
            'target_fat': forms.NumberInput(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
            'diet_style': forms.Select(attrs={'class': _NUTRITION_TARGET_WIDGET_CLASS}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        h = Household.objects.filter(owner=user).first() if user else None
        self.fields['assign_to_member'].queryset = (
            h.members.order_by('sort_order', 'id') if h else HouseholdMember.objects.none()
        )


def ensure_default_day_profiles(user):
    """Tipi giorno iniziali se l'utente non ne ha ancora creati (primo accesso)."""
    if DayProfile.objects.filter(owner=user).exists():
        return
    DayProfile.objects.create(owner=user, name='Riposo', order=0)
    DayProfile.objects.create(
        owner=user,
        name='Allenamento',
        order=1,
        notes='Es.: più carboidrati o kcal — personalizza o rinomina.',
    )


def monday_of_week(for_date: date | None = None) -> date:
    """Lunedì della settimana ISO che contiene ``for_date`` (default: oggi)."""
    d = for_date or date.today()
    return d - timedelta(days=d.weekday())


def get_catalog_stats_context():
    """Conteggio ingredienti e pasti di sistema (dashboard + partial HTMX)."""
    return {
        'ingredient_count': Ingredient.objects.count(),
        'meal_count': Meal.objects.filter(is_system=True).count(),
    }


def latest_target_for_member(user, member):
    """Target personale collegato al commensale via ``HouseholdMember.nutrition_target``."""
    t = member.nutrition_target
    if t and t.owner_id == user.id and not t.is_system:
        return t
    return None


def get_default_weekplan_nutrition_target(user):
    """
    Target suggerito per un nuovo ``WeekPlan`` (settimana corrente):
    piano già esistente → suo target; altrimenti ultimo target del primo commensale;
    altrimenti target personali senza membro o qualsiasi personale.
    """
    monday = monday_of_week()
    current_plan = (
        WeekPlan.objects.filter(owner=user, week_start=monday).select_related('nutrition_target').first()
    )
    if current_plan and current_plan.nutrition_target_id:
        return current_plan.nutrition_target

    household = Household.objects.filter(owner=user).first()
    if household:
        first_m = household.members.order_by('sort_order', 'id').first()
        if first_m:
            nt = latest_target_for_member(user, first_m)
            if nt:
                return nt

    unlinked = (
        NutritionTarget.objects.filter(owner=user, is_system=False)
        .annotate(_n_members=Count('linked_household_members'))
        .filter(_n_members=0)
        .order_by('-created_at')
        .first()
    )
    if unlinked:
        return unlinked
    return NutritionTarget.objects.filter(owner=user, is_system=False).order_by('-created_at').first()


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    user = request.user
    household = Household.ensure_for_user(user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'assign_member_target':
            try:
                mid = int(request.POST.get('member_id', ''))
            except (TypeError, ValueError):
                messages.error(request, 'Membro non valido.')
                return redirect('core:dashboard')
            member = HouseholdMember.objects.filter(id=mid, household__owner=user).first()
            if not member:
                messages.error(request, 'Membro non trovato.')
                return redirect('core:dashboard')
            raw_tid = request.POST.get('nutrition_target_id', '').strip()
            if not raw_tid:
                member.nutrition_target = None
                member.save(update_fields=['nutrition_target'])
                messages.success(request, 'Nessun target collegato a questo commensale.')
                return redirect('core:dashboard')
            try:
                tid = int(raw_tid)
            except (TypeError, ValueError):
                messages.error(request, 'Target non valido.')
                return redirect('core:dashboard')
            nt = NutritionTarget.objects.filter(id=tid, owner=user, is_system=False).first()
            if not nt:
                messages.error(request, 'Target non trovato.')
                return redirect('core:dashboard')
            member.nutrition_target = nt
            member.save(update_fields=['nutrition_target'])
            messages.success(request, f'Target «{nt.name}» collegato a {member.display_name}.')
            return redirect('core:dashboard')

        return redirect('core:dashboard')

    members = list(household.members.order_by('sort_order', 'id'))
    assignable = (
        NutritionTarget.objects.filter(owner=user, is_system=False)
        .prefetch_related('linked_household_members')
        .order_by('-created_at')
    )
    member_rows = []
    for m in members:
        member_rows.append(
            {
                'member': m,
                'active_target': latest_target_for_member(user, m),
                'assignable_targets': assignable,
            }
        )

    context = {
        **get_catalog_stats_context(),
        'household': household,
        'member_rows': member_rows,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def nutrition_target_create(request):
    """Pagina dedicata: crea un target personale; collegamento commensale opzionale."""
    user = request.user
    household = Household.ensure_for_user(user)

    initial = {}
    membro = request.GET.get('membro')
    if membro:
        try:
            mid = int(membro)
        except (TypeError, ValueError):
            pass
        else:
            if household.members.filter(pk=mid).exists():
                initial['assign_to_member'] = mid

    if request.method == 'POST':
        form = NutritionTargetCreateForm(request.POST, user=user)
        if form.is_valid():
            member = form.cleaned_data.get('assign_to_member')
            nt = form.save(commit=False)
            nt.owner = user
            nt.is_system = False
            nt.save()
            if member:
                member.nutrition_target = nt
                member.save(update_fields=['nutrition_target'])
                messages.success(
                    request,
                    f'Target «{nt.name}» creato e collegato a {member.display_name}.',
                )
            else:
                messages.success(request, f'Target «{nt.name}» creato.')
            return redirect('core:dashboard')
    else:
        form = NutritionTargetCreateForm(user=user, initial=initial)

    return render(
        request,
        'core/nutrition_target_create.html',
        {'form': form, 'household': household},
    )


@login_required
@require_http_methods(['GET', 'POST'])
def week_plan_current(request):
    """
    Piano settimanale: griglia pasti, tipo di giorno per colonna (allenamento/…),
    presenza commensali agli slot con pasto.
    """
    user = request.user
    monday = monday_of_week()

    week_plan, _created = WeekPlan.objects.get_or_create(
        owner=user,
        week_start=monday,
        defaults={
            'is_system': False,
            'nutrition_target': get_default_weekplan_nutrition_target(user),
        },
    )

    ensure_default_day_profiles(user)
    household = Household.ensure_for_user(user)
    members = list(household.members.all())
    day_profiles = list(DayProfile.objects.filter(owner=user).order_by('order', 'id'))

    slots_qs = (
        WeekPlanSlot.objects.filter(week_plan=week_plan)
        .select_related('meal_slot', 'meal')
        .order_by('day', 'meal_slot__order')
    )
    slots_list = list(slots_qs)
    slots_with_meal = [s for s in slots_list if s.meal_id]

    if request.method == 'POST':
        form_id = request.POST.get('form_id')
        if form_id == 'day_kinds':
            for d in range(7):
                raw = request.POST.get(f'day_kind_{d}', '').strip()
                if not raw:
                    WeekPlanDayKind.objects.filter(week_plan=week_plan, day=d).delete()
                    continue
                try:
                    pid = int(raw)
                except (TypeError, ValueError):
                    continue
                dp = DayProfile.objects.filter(id=pid, owner=user).first()
                if not dp:
                    continue
                WeekPlanDayKind.objects.update_or_create(
                    week_plan=week_plan,
                    day=d,
                    defaults={'day_profile': dp},
                )
            messages.success(request, 'Tipi di giorno aggiornati per questa settimana.')
            return redirect('core:week_plan')

        if form_id == 'slot_attendance':
            members_by_id = {m.id: m for m in members}
            for slot in slots_with_meal:
                WeekPlanSlotAttendance.objects.filter(slot=slot).delete()
                for mid_str in request.POST.getlist(f'attend_{slot.id}'):
                    try:
                        mid = int(mid_str)
                    except (TypeError, ValueError):
                        continue
                    member = members_by_id.get(mid)
                    if member is None:
                        continue
                    WeekPlanSlotAttendance.objects.create(slot=slot, household_member=member)
            messages.success(request, 'Presenza ai pasti aggiornata.')
            return redirect('core:week_plan')

    day_kind_map = {
        row.day: row.day_profile_id
        for row in WeekPlanDayKind.objects.filter(week_plan=week_plan).only('day', 'day_profile_id')
    }
    day_kind_columns = [
        {'day': d, 'label': WeekDay(d).label, 'current_profile_id': day_kind_map.get(d)}
        for d in range(7)
    ]

    attendance_by_slot = {}
    for sid, mid in WeekPlanSlotAttendance.objects.filter(slot__week_plan=week_plan).values_list(
        'slot_id', 'household_member_id'
    ):
        attendance_by_slot.setdefault(sid, set()).add(mid)

    attendance_slots_ui = []
    for slot in slots_with_meal:
        present = attendance_by_slot.get(slot.id, set())
        attendance_slots_ui.append(
            {
                'slot': slot,
                'members_checked': [(m, m.id in present) for m in members],
            }
        )

    meal_slots = list(MealSlot.objects.filter(user=user).order_by('order'))

    by_day_slot = {
        (s.day, s.meal_slot_id): s.meal
        for s in slots_list
    }

    grid_rows = []
    for slot in meal_slots:
        cells = []
        for day in range(7):
            meal = by_day_slot.get((day, slot.id))
            cells.append({'day': day, 'meal': meal})
        grid_rows.append({'slot': slot, 'cells': cells})

    week_day_headers = [(d, WeekDay(d).label) for d in range(7)]

    nutrition_totals = compute_week_totals(user, week_plan, slots_with_meal, members)
    context = {
        'week_plan': week_plan,
        'week_start': monday,
        'meal_slots': meal_slots,
        'grid_rows': grid_rows,
        'week_day_headers': week_day_headers,
        'day_profiles': day_profiles,
        'day_kind_columns': day_kind_columns,
        'household': household,
        'members': members,
        'slots_with_meal': slots_with_meal,
        'attendance_slots_ui': attendance_slots_ui,
        'nutrition_totals': nutrition_totals,
    }
    return render(request, 'core/week_plan.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def household_manage(request):
    """CRUD minimo commensali del nucleo familiare (un nucleo per utente)."""
    household = Household.ensure_for_user(request.user)
    members = list(household.members.order_by('sort_order', 'id'))

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            form = AddHouseholdMemberForm(request.POST)
            if form.is_valid():
                name = form.cleaned_data['display_name'].strip()
                if name:
                    max_so = household.members.aggregate(m=Max('sort_order'))['m']
                    next_so = (max_so if max_so is not None else -1) + 1
                    HouseholdMember.objects.create(
                        household=household,
                        display_name=name,
                        sort_order=next_so,
                    )
                    messages.success(request, f'Commensale «{name}» aggiunto.')
            return redirect('core:household')
        if action == 'delete':
            mid = request.POST.get('member_id')
            try:
                mid = int(mid)
            except (TypeError, ValueError):
                messages.error(request, 'Richiesta non valida.')
                return redirect('core:household')
            if household.members.count() <= 1:
                messages.error(request, 'Serve almeno un commensale nel nucleo.')
                return redirect('core:household')
            deleted, _ = HouseholdMember.objects.filter(id=mid, household=household).delete()
            if deleted:
                messages.success(request, 'Commensale rimosso.')
            else:
                messages.error(request, 'Commensale non trovato.')
            return redirect('core:household')

    form = AddHouseholdMemberForm()
    return render(
        request,
        'core/household.html',
        {
            'household': household,
            'members': members,
            'form': form,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def day_profiles_manage(request):
    """Elenco e creazione tipi di giorno (Allenamento, Riposo, …)."""
    user = request.user
    ensure_default_day_profiles(user)
    profiles = list(DayProfile.objects.filter(owner=user).order_by('order', 'id'))

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            form = AddDayProfileForm(request.POST)
            if form.is_valid():
                name = form.cleaned_data['name'].strip()
                if name:
                    if DayProfile.objects.filter(owner=user, name__iexact=name).exists():
                        messages.error(request, 'Esiste già un tipo con questo nome.')
                    else:
                        max_o = DayProfile.objects.filter(owner=user).aggregate(m=Max('order'))['m']
                        next_o = (max_o if max_o is not None else -1) + 1
                        DayProfile.objects.create(
                            owner=user,
                            name=name,
                            order=next_o,
                            notes=(form.cleaned_data.get('notes') or '').strip(),
                        )
                        messages.success(request, f'Tipo «{name}» creato.')
            return redirect('core:day_profiles')
        if action == 'delete':
            pid = request.POST.get('profile_id')
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                messages.error(request, 'Richiesta non valida.')
                return redirect('core:day_profiles')
            if DayProfile.objects.filter(owner=user).count() <= 1:
                messages.error(request, 'Serve almeno un tipo di giorno.')
                return redirect('core:day_profiles')
            deleted, _ = DayProfile.objects.filter(id=pid, owner=user).delete()
            if deleted:
                messages.success(request, 'Tipo rimosso.')
            else:
                messages.error(request, 'Tipo non trovato.')
            return redirect('core:day_profiles')
        if action == 'save_modifiers':
            household = Household.ensure_for_user(user)
            members = list(household.members.order_by('sort_order', 'id'))
            profiles = list(DayProfile.objects.filter(owner=user))
            errors = []
            for profile in profiles:
                for member in members:
                    prefix = f'mod_{profile.id}_{member.id}_'
                    raw = {
                        'kcal_factor': request.POST.get(prefix + 'kcal', '1.00'),
                        'protein_factor': request.POST.get(prefix + 'protein', '1.00'),
                        'carbs_factor': request.POST.get(prefix + 'carbs', '1.00'),
                        'fat_factor': request.POST.get(prefix + 'fat', '1.00'),
                    }
                    try:
                        values = {k: Decimal(v.strip().replace(',', '.')) for k, v in raw.items()}
                    except (InvalidOperation, AttributeError):
                        errors.append(f'{profile.name} / {member.display_name}: valore non valido.')
                        continue
                    if any(v <= 0 for v in values.values()):
                        errors.append(f'{profile.name} / {member.display_name}: i fattori devono essere > 0.')
                        continue
                    # Fattori tutti a 1.00 = nessuna variazione -> non serve salvare la riga,
                    # la teniamo solo se almeno un fattore si discosta dal default.
                    if all(v == Decimal('1.00') for v in values.values()):
                        DayProfileMemberModifier.objects.filter(
                            day_profile=profile, household_member=member
                        ).delete()
                        continue
                    DayProfileMemberModifier.objects.update_or_create(
                        day_profile=profile, household_member=member, defaults=values,
                    )
            if errors:
                for e in errors[:5]:  # evita flood di messaggi se la matrice è grande
                    messages.error(request, e)
            else:
                messages.success(request, 'Fattori nutrizionali per tipo giorno aggiornati.')
            return redirect('core:day_profiles')

    form = AddDayProfileForm()
    household = Household.ensure_for_user(user)
    members = list(household.members.order_by('sort_order', 'id'))
    existing_modifiers = {
        (m.day_profile_id, m.household_member_id): m
        for m in DayProfileMemberModifier.objects.filter(day_profile__owner=user)
    }
    modifier_matrix = []
    for profile in profiles:
        member_rows = []
        for member in members:
            mod = existing_modifiers.get((profile.id, member.id))
            member_rows.append({
                'member': member,
                'kcal_factor': mod.kcal_factor if mod else Decimal('1.00'),
                'protein_factor': mod.protein_factor if mod else Decimal('1.00'),
                'carbs_factor': mod.carbs_factor if mod else Decimal('1.00'),
                'fat_factor': mod.fat_factor if mod else Decimal('1.00'),
            })
        modifier_matrix.append({'profile': profile, 'member_rows': member_rows})

    return render(
        request,
        'core/day_profiles.html',
        {'profiles': profiles, 'form': form, 'modifier_matrix': modifier_matrix},
    )


def register(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)          # login automatico post-registrazione
            return redirect('core:dashboard')
    else:
        form = UserCreationForm()

    return render(request, 'registration/register.html', {'form': form})


@login_required
def catalog_partial(request):
    return render(request, 'core/_catalog_section.html', get_catalog_stats_context())