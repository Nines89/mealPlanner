"""Fixed ON / OFF nutrition targets (kcal + macro % ranges)."""
from decimal import Decimal, ROUND_HALF_UP

from .models import DayKind, DietStyle, MealSlotTarget, NutritionTarget, UserProfile, WeekPlan, WeekPlanDayKind

KCAL_PER_GRAM = {
    'protein': Decimal('4'),
    'carbs': Decimal('4'),
    'fat': Decimal('9'),
}

# Same split for ON and OFF; only total kcal changes.
MACRO_PCT = {
    'protein': (15, 25),
    'fat': (20, 25),
    'carbs': (45, 50),
}

TARGET_SPECS = (
    {
        'kind': DayKind.ON,
        'name': 'ON',
        'target_kcal': 1700,
    },
    {
        'kind': DayKind.OFF,
        'name': 'OFF',
        'target_kcal': 1500,
    },
)


def midpoint_grams(kcal, pct_min, pct_max, kcal_per_gram):
    mid = (Decimal(pct_min) + Decimal(pct_max)) / Decimal('2') / Decimal('100')
    grams = Decimal(kcal) * mid / Decimal(kcal_per_gram)
    return int(grams.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def spec_grams_for(kcal, protein_pct=None, carbs_pct=None, fat_pct=None):
    p_lo, p_hi = protein_pct or MACRO_PCT['protein']
    c_lo, c_hi = carbs_pct or MACRO_PCT['carbs']
    f_lo, f_hi = fat_pct or MACRO_PCT['fat']
    return {
        'target_protein': midpoint_grams(kcal, p_lo, p_hi, KCAL_PER_GRAM['protein']),
        'target_carbs': midpoint_grams(kcal, c_lo, c_hi, KCAL_PER_GRAM['carbs']),
        'target_fat': midpoint_grams(kcal, f_lo, f_hi, KCAL_PER_GRAM['fat']),
        'protein_pct_min': p_lo,
        'protein_pct_max': p_hi,
        'carbs_pct_min': c_lo,
        'carbs_pct_max': c_hi,
        'fat_pct_min': f_lo,
        'fat_pct_max': f_hi,
    }


def apply_midpoint_grams(nt):
    """Set gram fields to the midpoints of the stored % ranges."""
    grams = spec_grams_for(
        nt.target_kcal,
        (nt.protein_pct_min, nt.protein_pct_max),
        (nt.carbs_pct_min, nt.carbs_pct_max),
        (nt.fat_pct_min, nt.fat_pct_max),
    )
    nt.target_protein = grams['target_protein']
    nt.target_carbs = grams['target_carbs']
    nt.target_fat = grams['target_fat']
    return nt


def _delete_other_targets():
    keep_kinds = [DayKind.ON, DayKind.OFF]
    others = NutritionTarget.objects.exclude(kind__in=keep_kinds)
    if not others.exists():
        return
    WeekPlan.objects.filter(nutrition_target__in=others).update(nutrition_target=None)
    UserProfile.objects.filter(nutrition_target__in=others).update(nutrition_target=None)
    MealSlotTarget.objects.filter(nutrition_target__in=others).delete()
    others.delete()


def ensure_on_off_targets():
    """Create the two ON/OFF rows if missing. Do not overwrite admin edits."""
    off = None
    for spec in TARGET_SPECS:
        grams = spec_grams_for(spec['target_kcal'])
        nt, _created = NutritionTarget.objects.get_or_create(
            kind=spec['kind'],
            defaults={
                'name': spec['name'],
                'owner': None,
                'is_system': True,
                'target_kcal': spec['target_kcal'],
                'diet_style': DietStyle.NONE,
                **grams,
            },
        )
        if spec['kind'] == DayKind.OFF:
            off = nt
    _delete_other_targets()
    return off


def get_target_by_kind(kind):
    ensure_on_off_targets()
    kind = kind or DayKind.OFF
    nt = NutritionTarget.objects.filter(kind=kind).first()
    if nt:
        return nt
    return NutritionTarget.objects.filter(kind=DayKind.OFF).first()


def day_kind_map(week_plan):
    """{day: 'on'|'off'} for a week; missing days default to OFF."""
    rows = WeekPlanDayKind.objects.filter(week_plan=week_plan).only('day', 'kind')
    found = {row.day: row.kind for row in rows}
    return {d: found.get(d) or DayKind.OFF for d in range(7)}


def targets_by_day(week_plan):
    ensure_on_off_targets()
    kinds = day_kind_map(week_plan)
    by_kind = {nt.kind: nt for nt in NutritionTarget.objects.filter(kind__in=[DayKind.ON, DayKind.OFF])}
    off = by_kind.get(DayKind.OFF)
    return {day: by_kind.get(kind, off) for day, kind in kinds.items()}
