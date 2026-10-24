import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .notion_sync import apply_plan, build_plan, fetch_notion_recipes, prepare_payload

logger = logging.getLogger(__name__)

SESSION_KEY = 'notion_sync_payload'
TEMPLATE = 'core/recipes_sync.html'


@login_required
@require_http_methods(['GET', 'POST'])
def recipes_sync(request):
    """GET: pagina col pulsante. POST preview: confronto. POST apply: scrittura."""
    if request.method == 'GET':
        return redirect('core:recipes')
    if request.POST.get('action') == 'apply':
        return _apply(request)
    return _preview(request)


def _preview(request):
    try:
        payload = prepare_payload(fetch_notion_recipes())
    except NotImplementedError:
        messages.error(request, 'Connettore Notion non ancora implementato.')
        return redirect('core:recipes')
    except Exception:  # noqa: BLE001 — errori di rete/auth della libreria esterna
        logger.exception('Lettura ricette da Notion fallita')
        messages.error(request, 'Lettura da Notion fallita (dettagli nel log).')
        return redirect('core:recipes')
    request.session[SESSION_KEY] = payload
    plan = build_plan(request.user, payload)
    return render(request, TEMPLATE, {'plan': plan})


def _apply(request):
    payload = request.session.pop(SESSION_KEY, None)
    if not payload:
        messages.error(request, 'Anteprima scaduta: rigenerala prima di applicare.')
        return redirect('core:recipes')
    # Ricalcolo sul DB attuale: si applica ciò che è stato visto, ma con diff fresco.
    plan = build_plan(request.user, payload)
    result = apply_plan(plan, request.user, prune=request.POST.get('prune') == '1')
    messages.success(
        request,
        f'Sync completato: {result.created} create, {result.updated} aggiornate, '
        f'{result.unchanged} invariate, {result.errors} con errori'
        + (f', {result.pruned} rimosse' if result.pruned else '')
        + (f' ({result.prune_skipped} non rimosse: usate in un piano)'
           if result.prune_skipped else '')
        + '.',
    )
    return redirect('core:recipes')
