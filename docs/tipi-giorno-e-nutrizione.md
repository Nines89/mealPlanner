# Tipi di giorno e nutrizione (design)

## Cosa c’è oggi nel codice

- **`DayProfile`**: etichette definite dal planner (es. «Riposo», «Allenamento»). Un elenco per utente.
- **`WeekPlanDayKind`**: per ogni **settimana** (`WeekPlan`) e ogni **giorno** (0 = lunedì … 6 = domenica), quale `DayProfile` applicare, oppure vuoto (giorno non classificato).
- **UI**: pagina `/tipi-giorno/` (CRUD tipi), barra sul **piano settimanale** con 7 select + salva.

Alla **prima** visita che richiede i tipi giorno, se non ne hai nessuno vengono creati **Riposo** e **Allenamento** (`ensure_default_day_profiles` in `core/views.py`).

## Perché separare «tipo giorno» dai target

Il tipo di giorno descrive **il contesto** (allenamento sì/no, turno, ecc.). I **target nutrizionali** restano entità proprie (`NutritionTarget`); ogni **commensale** ha un FK opzionale `nutrition_target` verso un target del planner (più persone possono condividere lo stesso target). Collegarli così evita duplicare righe target ogni settimana.

## Come evolvere (macro / diete diverse per tipo giorno)

Strade comuni (da scegliere in base a complessità desiderata):

1. **Target multipli per membro + profilo giorno**  
   Estendere `NutritionTarget` (o tabella ponte) con `day_profile` opzionale: stesso membro ha target «base» e target «allenamento». In aggregazione giornaliera si usa il target associato al `DayProfile` del giorno letto da `WeekPlanDayKind`.

2. **Moltiplicatori / offset sul target base**  
   Tabella `DayProfileNutritionModifier` (es. `kcal_factor = 1.1` per «Allenamento»). I macro del giorno = target collegato al membro × fattore del profilo del giorno.

3. **Pasti suggeriti per profilo** (non solo numeri)  
   Regole fisse: se giorno = Allenamento → priorità pasti ricchi di carboidrati; se Riposo → … (solo algoritmi, niente ML).

La **lista spesa** e i **totali settimanali** dovrebbero usare, per ogni data, il tipo giorno risolto da `WeekPlanDayKind` + presenza commensali + porzioni.

## Riferimenti codice

- Modelli: `core/models.py` — `DayProfile`, `WeekPlanDayKind`.
- Vista tipi: `day_profiles_manage`, URL `tipi-giorno/`.
- Vista piano: `week_plan_current` — `form_id=day_kinds`.
