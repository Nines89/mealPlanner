# Day types and nutrition — ON / OFF

**Status (2026-08):** The household uses **two targets** (ON / OFF). Defaults are 1700 / 1500 kcal; change kcal and % ranges in Django admin. Each weekday on the week plan is **ON** or **OFF**. Fill, slot budgets, and expected totals use that day’s target. Shopping is still one plate × household size (no attendance).

Do not rebuild per-member modifiers, attendance, or extra custom targets.

---

## Targets

| Kind | kcal | Protein | Fat | Carbs |
| --- | --- | --- | --- | --- |
| **ON** | 1700 | 15–25% | 20–25% | 45–50% |
| **OFF** | 1500 | 15–25% | 20–25% | 45–50% |

Gram fields on `NutritionTarget` are **midpoints** of those ranges (filler needs a single number). Defaults are seeded by `core/targets.py` (`ensure_on_off_targets`) if the rows are missing; later admin edits are kept. Change kcal and % in `/admin/` — grams update on save.

Default weekday: **OFF**.

## Schema

- **`NutritionTarget.kind`**: `on` or `off` (unique). Only these two rows should exist.
- **`WeekPlanDayKind.kind`**: ON/OFF for one weekday of a `WeekPlan`.
- **`DayProfile`**: unused leftover labels; do not wire back into the UI.

## Totals

Expected for a day = that day’s ON or OFF target × household size. Week expected sums the seven days.

## Portions

Lunch and dinner grams are computed from that day’s ON/OFF target (`core/planning.py`). Catalog/recipe weights are ignored. Each slot starts at half of the day (unless `MealSlotTarget` overrides the share). When both meals exist, they are scaled together so combined kcal/protein/carbs/fat land in **85–100%** of the day’s target.
