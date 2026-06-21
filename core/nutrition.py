"""
Calcolo totali nutrizionali per il piano settimanale.

Due quantità distinte, sempre tenute separate:
- "atteso"    = target del membro per quel GIORNO, eventualmente corretto dal fattore
                del DayProfile assegnato a quel giorno. È un valore "al giorno", non si
                somma per ogni pasto: un membro ha un solo target giornaliero, non uno
                per slot. Non dipende dai pasti pianificati.
- "effettivo" = somma macro degli ingredienti dei pasti pianificati, solo per i membri
                presenti allo slot (porzione per-membro se esiste, altrimenti porzione base).
                Dipende interamente da cosa è stato pianificato; è 0 se non c'è nulla.

Il confronto atteso/effettivo è il punto della Fase 3: non si confondono i due valori,
e l'atteso resta visibile anche quando non è stato pianificato ancora nessun pasto.
"""
from collections import defaultdict
from decimal import Decimal

from .models import (
    DayProfileMemberModifier,
    MealIngredientMemberPortion,
    WeekPlanDayKind,
    WeekPlanSlotAttendance,
)

ZERO = Decimal('0')

_MACROS = ('kcal', 'protein', 'carbs', 'fat')
_DAYS = range(7)


def _empty_macros():
    return {m: ZERO for m in _MACROS}


def _sum_macros(a, b):
    return {m: a[m] + b[m] for m in _MACROS}


def get_day_modifiers_map(user):
    """
    {(day_profile_id, household_member_id): {'kcal': factor, 'protein': factor, ...}}
    Combinazioni assenti = nessun modificatore esplicito (il chiamante usa fattore 1.0).
    """
    rows = DayProfileMemberModifier.objects.filter(day_profile__owner=user)
    out = {}
    for r in rows:
        out[(r.day_profile_id, r.household_member_id)] = {
            'kcal': r.kcal_factor,
            'protein': r.protein_factor,
            'carbs': r.carbs_factor,
            'fat': r.fat_factor,
        }
    return out


def expected_macros_for_member_day(member, day_profile_id, modifiers_map):
    """
    Target atteso per un membro in un giorno con un certo DayProfile (o None = giorno
    senza tipo assegnato). Nessun nutrition_target collegato -> None (assenza di dato,
    non un dato a zero: il template distingue "non impostato" da "zero kcal").
    """
    nt = member.nutrition_target
    if nt is None:
        return None

    base = {
        'kcal': Decimal(nt.target_kcal),
        'protein': Decimal(nt.target_protein),
        'carbs': Decimal(nt.target_carbs),
        'fat': Decimal(nt.target_fat),
    }
    if day_profile_id is None:
        return base

    factors = modifiers_map.get((day_profile_id, member.id))
    if factors is None:
        return base

    return {m: (base[m] * factors[m]) for m in _MACROS}


def effective_macros_for_slot(slot, present_member_ids):
    """
    Somma macro effettiva di uno slot (meal assegnata), solo per i membri presenti.
    Per ciascun MealIngredient: usa la porzione specifica del membro se esiste,
    altrimenti la porzione base (grams) — fallback esplicito, non implicito.
    Ritorna: {member_id: {'kcal':…, 'protein':…, 'carbs':…, 'fat':…}}
    """
    result = {mid: _empty_macros() for mid in present_member_ids}
    if not slot.meal_id or not present_member_ids:
        return result

    meal_ingredients = slot.meal.meal_ingredients.select_related('ingredient').all()
    mi_ids = [mi.id for mi in meal_ingredients]
    member_portions = defaultdict(dict)  # {meal_ingredient_id: {member_id: grams}}
    if mi_ids:
        for mp in MealIngredientMemberPortion.objects.filter(
            meal_ingredient_id__in=mi_ids, household_member_id__in=present_member_ids
        ):
            member_portions[mp.meal_ingredient_id][mp.household_member_id] = mp.grams

    for mi in meal_ingredients:
        ing = mi.ingredient
        per_member_grams = member_portions.get(mi.id, {})
        for mid in present_member_ids:
            grams = per_member_grams.get(mid, mi.grams)  # fallback su porzione base
            ratio = Decimal(grams) / Decimal('100')
            result[mid]['kcal'] += ing.kcal * ratio
            result[mid]['protein'] += ing.protein * ratio
            result[mid]['carbs'] += ing.carbs * ratio
            result[mid]['fat'] += ing.fat * ratio

    return result


def compute_week_totals(user, week_plan, slots_with_meal, members):
    """
    Totali atteso/effettivo per slot, per giorno e per settimana.

    - by_slot:  solo "effettivo" (l'atteso non ha senso per singolo pasto, vedi sopra).
    - by_day:   "expected" = target del giorno (membro × fattore profilo del giorno),
                presente per OGNI membro con nutrition_target, indipendentemente dal
                fatto che quel giorno abbia pasti pianificati o presenze.
                "effective" = somma dei pasti pianificati in quel giorno, solo presenti.
    - by_week:  "expected" = somma dei 7 valori giornalieri (by_day).
                "effective" = somma di tutti gli "effective" giornalieri.

    Ritorna:
    {
      'by_slot':  {slot_id: {member_id: {'effective': {...}}}},
      'by_day':   {day: {member_id: {'expected': {...}|None, 'effective': {...}}}},
      'by_week':  {member_id: {'expected': {...}|None, 'effective': {...}}},
    }
    """
    modifiers_map = get_day_modifiers_map(user)
    day_kind_map = {
        row.day: row.day_profile_id
        for row in WeekPlanDayKind.objects.filter(week_plan=week_plan).only('day', 'day_profile_id')
    }

    attendance_by_slot = defaultdict(set)
    for sid, mid in WeekPlanSlotAttendance.objects.filter(slot__week_plan=week_plan).values_list(
        'slot_id', 'household_member_id'
    ):
        attendance_by_slot[sid].add(mid)

    members_by_id = {m.id: m for m in members}

    # --- 1) ATTESO per giorno: indipendente dai pasti pianificati, calcolato per TUTTI i membri.
    by_day = {day: {} for day in _DAYS}
    for day in _DAYS:
        day_profile_id = day_kind_map.get(day)
        for member in members:
            expected = expected_macros_for_member_day(member, day_profile_id, modifiers_map)
            by_day[day][member.id] = {'expected': expected, 'effective': _empty_macros()}

    # --- 2) EFFETTIVO per slot: dipende dai pasti pianificati e da chi è presente.
    by_slot = {}
    for slot in slots_with_meal:
        present_ids = attendance_by_slot.get(slot.id, set())
        effective_map = effective_macros_for_slot(slot, present_ids)

        slot_entry = {}
        for mid in present_ids:
            if mid not in members_by_id:
                continue
            effective = effective_map.get(mid, _empty_macros())
            slot_entry[mid] = {'effective': effective}
            # Accumula nell'effettivo del giorno (più slot nello stesso giorno si sommano).
            by_day[slot.day][mid]['effective'] = _sum_macros(
                by_day[slot.day][mid]['effective'], effective
            )
        by_slot[slot.id] = slot_entry

    # --- 3) Settimana: somma dei 7 giorni.
    by_week = {}
    for member in members:
        week_expected = None
        week_effective = _empty_macros()
        for day in _DAYS:
            entry = by_day[day][member.id]
            if entry['expected'] is not None:
                week_expected = _sum_macros(week_expected or _empty_macros(), entry['expected'])
            week_effective = _sum_macros(week_effective, entry['effective'])
        by_week[member.id] = {'expected': week_expected, 'effective': week_effective}

    return {'by_slot': by_slot, 'by_day': by_day, 'by_week': by_week}