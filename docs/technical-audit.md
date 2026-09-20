# Audit tecnico e piano di pulizia

## Correzioni applicate

- **Autenticazione:** le pagine che leggono o modificano piani familiari richiedono ora una sessione autenticata; l'API, già protetta da DRF, è finalmente pubblicata sotto `/api/ingredients/`.
- **Sviluppo locale:** il precedente login automatico non è più attivo implicitamente. È un'opzione esplicita, limitata a `DJANGO_DEBUG=True`, così un deploy non può servire per errore i dati del primo utente del database.
- **Configurazione sicura:** chiave segreta, host e origini CSRF sono configurazione d'ambiente. In produzione l'applicazione non si avvia senza questi valori, anziché usare una chiave versionata e `ALLOWED_HOSTS=['*']`.
- **HTTP:** cookie sicuri, redirect HTTPS, HSTS, `nosniff`, referrer policy e protezione anti-frame sono abilitati fuori dal debug. Il redirect HTTPS è configurabile per un reverse proxy.

## Debito tecnico da rimuovere in seguito

1. **Modello dati storico.** `DayProfile`, `MealSlotTarget` e vari campi `is_system`/`owner` sono in parte dichiarati inutilizzati nei docstring. Prima di eliminarli serve esportare e classificare i dati reali, quindi fare una migrazione di rimozione dedicata e aggiornare admin/test.
2. **Invarianti solo in Python.** I metodi `clean()` di Django non vengono eseguiti da `save()` o dai bulk update. Le relazioni `WeekPlanSlot → MealSlot/Meal` e le percentuali dei target meritano vincoli DB dove esprimibili, più validazione nel service layer per le invarianti cross-table.
3. **Scritture durante le richieste.** La sincronizzazione di slot e target era eseguita dal middleware. È costosa, sorprendente e rischiosa sotto concorrenza; va sostituita completamente da migrazioni e da un comando esplicito di manutenzione idempotente.
4. **Accoppiamento UI/dominio.** `views.py` orchestra molte azioni e messaggi. I casi d'uso dovrebbero restituire risultati tipizzati dal layer `week.py`/`planning.py`, mentre le view fanno solo autorizzazione, form binding e rendering.
5. **Qualità di distribuzione.** Tailwind Play CDN e HTMX da CDN non sono asset riproducibili né hanno SRI/CSP. Compilare e versionare gli asset, introdurre CSP in modalità report-only e aggiungere CI (test, check deploy, migrazioni, formatter/linter e audit dipendenze).

## Metriche consigliate

- bloccare merge con `manage.py test`, `manage.py check --deploy`, `makemigrations --check`, formatter e linter;
- misurare query per dashboard/piano (`assertNumQueries` o Django Debug Toolbar solo in sviluppo) e p95 di risposta;
- tracciare errori applicativi, tasso di login falliti e copertura dei test dei flussi di autorizzazione;
- definire SLO per backup/ripristino del database e applicare gli aggiornamenti di sicurezza delle dipendenze con cadenza regolare.
