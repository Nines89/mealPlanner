(function () {
  'use strict';

  const sendForm = document.querySelector('[data-alexa-send-form]');
  const progress = document.querySelector('[data-alexa-progress]');
  if (sendForm && progress) {
    const title = progress.querySelector('[data-alexa-progress-title]');
    const message = progress.querySelector('[data-alexa-progress-message]');
    const elapsed = progress.querySelector('[data-alexa-elapsed]');
    const spinner = progress.querySelector('[data-alexa-spinner]');
    const dismiss = progress.querySelector('[data-alexa-dismiss]');
    let timer = null;

    function showProgress() {
      progress.classList.remove('hidden');
      progress.classList.add('flex');
      progress.setAttribute('aria-hidden', 'false');
      const startedAt = Date.now();
      timer = window.setInterval(() => {
        const totalSeconds = Math.floor((Date.now() - startedAt) / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = String(totalSeconds % 60).padStart(2, '0');
        elapsed.textContent = `${minutes}:${seconds}`;
      }, 1000);
    }

    function showError(text) {
      if (timer) window.clearInterval(timer);
      title.textContent = 'Invio non completato';
      message.textContent = text;
      spinner.classList.add('hidden');
      dismiss.classList.remove('hidden');
      dismiss.addEventListener('click', () => window.location.reload(), { once: true });
    }

    sendForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (sendForm.dataset.sending === 'true') return;
      sendForm.dataset.sending = 'true';
      const submitButton = sendForm.querySelector('[type="submit"]');
      if (submitButton) submitButton.disabled = true;
      showProgress();

      try {
        const response = await fetch(sendForm.action, {
          method: 'POST',
          body: new FormData(sendForm),
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        if (!result.ok) {
          title.textContent = 'Invio terminato';
          message.textContent = 'Aggiorno la pagina per mostrare il messaggio di esito.';
        } else {
          title.textContent = 'Invio completato';
          message.textContent = 'Alexa ha ricevuto gli elementi. Aggiorno la lista…';
        }
        if (timer) window.clearInterval(timer);
        window.setTimeout(() => window.location.reload(), 900);
      } catch (error) {
        showError('Non riesco a ricevere la risposta dal server. L’invio potrebbe essere ancora in corso; ricarica la pagina per controllare l’esito.');
      }
    });
  }

  const list = document.querySelector('[data-shopping-list]');
  if (!list) return;

  const body = list.querySelector('tbody');
  const status = document.querySelector('[data-shopping-status]');
  const csrfInput = list.querySelector('[data-order-csrf] [name=csrfmiddlewaretoken]');
  let draggedRow = null;
  let draggedHandle = null;
  let draggedPointerId = null;
  let orderChanged = false;

  function saveOrder() {
    if (!orderChanged) return;
    orderChanged = false;
    const items = Array.from(body.querySelectorAll('[data-shopping-row]')).map((row) => ({
      id: row.dataset.ingredient,
      section: row.dataset.section,
    }));
    if (status) status.textContent = 'Salvataggio ordine…';
    fetch(list.dataset.saveUrl, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfInput ? csrfInput.value : '',
      },
      body: JSON.stringify({ week: list.dataset.week, items }),
    }).then((response) => {
      if (!response.ok) throw new Error('Order save failed');
      if (status) status.textContent = 'Ordine salvato.';
    }).catch(() => {
      if (status) status.textContent = 'Impossibile salvare l’ordine.';
    });
  }

  function moveRelative(row, target, after) {
    if (!row || !target || row === target) return false;
    const reference = after ? target.nextElementSibling : target;
    if (reference === row || (!after && row.nextElementSibling === target)) return false;
    row.dataset.section = target.dataset.section;
    body.insertBefore(row, reference);
    orderChanged = true;
    return true;
  }

  function moveToHeading(row, heading) {
    if (!row || !heading || !heading.querySelector('th[colspan]') || row === heading.nextElementSibling) return false;
    row.dataset.section = heading.dataset.section;
    body.insertBefore(row, heading.nextElementSibling);
    orderChanged = true;
    return true;
  }

  body.querySelectorAll('tr').forEach((row) => {
    const heading = row.querySelector('th[colspan]');
    if (heading) {
      row.dataset.sectionHeading = '';
      const next = row.nextElementSibling;
      if (next) row.dataset.section = next.dataset.section;
      return;
    }
    if (!row.querySelector('[data-drag-handle]')) return;
    row.dataset.shoppingRow = '';
    row.dataset.ingredient = row.querySelector('[data-drag-handle]').dataset.ingredient;
    row.dataset.section = row.closest('tbody').querySelector('tr[data-section]')?.dataset.section || '';
  });

  // Attach each ingredient row to its current category heading.
  let currentSection = '';
  body.querySelectorAll('tr').forEach((row) => {
    if (row.querySelector('th[colspan]')) {
      currentSection = row.querySelector('th[colspan]').textContent.trim();
      row.dataset.section = currentSection;
    } else if (row.hasAttribute('data-shopping-row')) {
      row.dataset.section = currentSection;
    }
  });

  body.addEventListener('pointerdown', (event) => {
    const handle = event.target.closest('[data-drag-handle]');
    if (!handle || event.button !== 0) return;
    draggedHandle = handle;
    draggedRow = handle.closest('[data-shopping-row]');
    draggedPointerId = event.pointerId;
    body.setPointerCapture(event.pointerId);
    draggedRow.classList.add('opacity-50');
    event.preventDefault();
  });

  body.addEventListener('pointermove', (event) => {
    if (!draggedRow || !draggedHandle || event.pointerId !== draggedPointerId
        || !body.hasPointerCapture(event.pointerId)) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)
      ?.closest('[data-shopping-row], tr[data-section-heading]');
    if (!target || target === draggedRow) return;
    if (target.matches('[data-section-heading]')) {
      moveToHeading(draggedRow, target);
      return;
    }
    const box = target.getBoundingClientRect();
    moveRelative(draggedRow, target, event.clientY > box.top + box.height / 2);
  });

  function finishDrag() {
    if (!draggedRow) return;
    draggedRow.classList.remove('opacity-50');
    saveOrder();
    draggedRow = null;
    draggedHandle = null;
    draggedPointerId = null;
  }

  body.addEventListener('pointerup', finishDrag);
  body.addEventListener('pointercancel', finishDrag);
  window.addEventListener('pagehide', saveOrder);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') saveOrder();
  });

  body.addEventListener('keydown', (event) => {
    const handle = event.target.closest('[data-drag-handle]');
    if (!handle || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const row = handle.closest('[data-shopping-row]');
    const rows = Array.from(body.querySelectorAll('[data-shopping-row]'));
    const index = rows.indexOf(row);
    const target = rows[index + (event.key === 'ArrowUp' ? -1 : 1)];
    if (!target) return;
    event.preventDefault();
    moveRelative(row, target, event.key === 'ArrowDown');
    saveOrder();
    handle.focus();
    if (status) status.textContent = `${row.querySelector('[data-drag-handle]').getAttribute('aria-label').replace('Sposta ', '')} riordinato.`;
  });
})();
