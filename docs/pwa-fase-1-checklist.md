# PWA — Fase 1: installazione Android, smoke offline, strategia cache

Documento operativo per chiudere la **Fase 1** del roadmap (`.cursor/rules/django-meal-planner-pwa.mdc`). Aggiorna la regola del progetto quando questi punti risultano **fatti**.

---

## 1. Prerequisiti

| Requisito | Nota |
| --- | --- |
| **HTTPS o localhost** | Chrome installa la PWA solo in contesto sicuro. `runserver` su `127.0.0.1` / `localhost` è ok. Da **telefono sulla LAN** (`http://192.168.x.x:8000`) l’installazione **può fallire**: usa tunnel HTTPS (es. [ngrok](https://ngrok.com/)) o deploy di prova. |
| `DEBUG=True` e `ALLOWED_HOSTS` | Già compatibile con test in LAN se l’host è consentito (es. `['*']` in dev). |

---

## 2. Test installazione (Chrome Android)

1. Apri il sito in **Chrome** (stesso URL che userai in produzione, idealmente **HTTPS**).
2. Menu Chrome (⋮) → **Aggiungi a schermata Home** / **Installa app** (la voce dipende dalla versione).
3. Verifica dopo l’installazione:
   - **Icona** corretta (192/512 da `/static/pwa/`).
   - **Nome** breve: «Meal» (manifest `short_name`).
   - **Apertura standalone** (senza barra indirizzi), tema barra coerente con `theme_color`.

**Problemi frequenti**

- Nessuna voce «Installa»: apri **Chrome → Impostazioni sito** e controlla che il sito non sia bloccato; verifica **Applicazione** nei DevTools (da PC) che manifest e service worker siano validi.
- Icona bianca / default: controlla che `GET /manifest.webmanifest` mostri URL icone **assoluti** `https://…/static/pwa/…` raggiungibili.

---

## 3. Smoke test offline

**Comportamento atteso** (strategia documentata nello `sw.js`):

- Il service worker fa **cache-first solo su** `GET` verso path che iniziano con **`/static/`** (asset del progetto).
- **HTML, HTMX, API, admin**: sempre rete → **senza rete le pagine dinamiche non si caricano** (nessuna cache SW delle risposte utente).
- **Tailwind e HTMX da CDN**: non passano dallo SW → in offline **non** sono disponibili se non già in cache del browser.

**Procedura rapida**

1. Con rete attiva, apri l’home almeno una volta (così lo SW si installa e le icone vanno in cache; vedi precache in `core/pwa/sw.js`).
2. Attiva **modalità aereo** o disattiva Wi‑Fi/dati.
3. Ricarica: ti aspetti **errore di rete** sulla documento principale (normale con la strategia attuale).
4. Opzionale: in DevTools → **Application → Cache Storage**, verifica la presenza di `mealplanner-static-v…` con le icone.

Se in futuro servisse una **pagina offline** leggibile (solo messaggio «Sei offline»), va aggiunta una strategia dedicata (es. `fetch` + `catch` → `offline.html`) — oggi **non** è in scope per non mischiare sessioni/HTML utente nella cache SW.

---

## 4. Strategia cache (decisione registrata)

| Cosa | Strategia |
| --- | --- |
| Asset in `/static/` | Cache SW **network-first o cache-first** (implementazione: cache-first dopo primo hit; precache icone PWA). |
| HTML / API / HTMX | **Sempre rete** — niente cache nello SW per evitare contenuti sessione obsoleti o leak tra utenti. |
| CDN (Tailwind, HTMX) | Fuori dallo SW; offline limitato **per design**. |

Aggiornare questa tabella solo se si introduce `offline.html` o cache mirata per URL pubblici.

---

## 5. Verifica da desktop (prima del telefono)

- `py manage.py runserver` → `http://127.0.0.1:8000/`
- Chrome → **F12 → Application**:
  - **Manifest**: nessun errore rosso.
  - **Service Workers**: registrato, scope `/`, stato attivo.
- Opzionale: **Lighthouse** → categoria *Progressive Web App* (se disponibile nella tua versione di Chrome).

---

## 6. Dopo i test

- Segna nella regola del progetto: checklist PWA **completata** su dispositivo reale (sì/no + data breve).
- Se usi tunnel o staging, annota l’URL usato per il test (senza segreti).
