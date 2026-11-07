(function () {
  'use strict';

  const list = document.querySelector('[data-shopping-list]');
  if (!list) return;

  const body = list.querySelector('tbody');
  const status = document.querySelector('[data-shopping-status]');
  const csrfInput = list.querySelector('[data-order-csrf] [name=csrfmiddlewaretoken]');
  let draggedRow = null;
  let draggedHandle = null;
  let draggedPointerId = null;

  function saveOrder() {
    const items = Array.from(body.querySelectorAll('[data-shopping-row]')).map((row) => ({
      id: Number(row.dataset.ingredient),
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
    return true;
  }

  function moveToHeading(row, heading) {
    if (!row || !heading || !heading.querySelector('th[colspan]') || row === heading.nextElementSibling) return false;
    row.dataset.section = heading.dataset.section;
    body.insertBefore(row, heading.nextElementSibling);
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
