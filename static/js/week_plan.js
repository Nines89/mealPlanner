(function () {
  const SCROLL_KEY = 'mealplanner-week-scroll';
  const DRAG_THRESHOLD = 8;
  const root = document.querySelector('[data-week-plan]');
  if (!root) {
    return;
  }

  const hint = root.querySelector('[data-plan-hint]');
  const live = root.querySelector('[data-plan-live]');
  const form = document.getElementById('week-plan-form');
  const formIdInput = root.querySelector('[data-week-form-id]');
  const rebuildDayInput = root.querySelector('[data-rebuild-day]');
  const rebuildSlotInput = root.querySelector('[data-rebuild-slot]');
  const picker = root.querySelector('[data-genre-picker]');
  const pickerTitle = root.querySelector('[data-picker-title]');
  const defaultHint = hint ? hint.textContent : '';
  let selectedGenre = '';
  let pickerCell = null;
  let drag = null;
  let ignoreClick = false;

  root.classList.add('is-ready');
  bindBoard();
  keepWeekScroll();

  function bindBoard() {
    root.querySelectorAll('[data-genre-chip]').forEach(function (chip) {
      chip.addEventListener('pointerdown', onPalettePointerDown);
      chip.addEventListener('click', onPaletteClick);
    });
    root.querySelectorAll('[data-drop-cell]').forEach(function (cell) {
      cell.addEventListener('click', onCellClick);
      refreshCell(cell);
    });
    root.querySelectorAll('[data-change-category]').forEach(function (button) {
      button.addEventListener('click', onChangeCategoryClick);
    });
    root.querySelectorAll('[data-clear-cell]').forEach(function (button) {
      button.addEventListener('click', onClearClick);
    });
    root.querySelectorAll('[data-kind-toggle]').forEach(function (button) {
      button.addEventListener('click', onKindToggle);
    });
    root.querySelectorAll('[data-picker-dismiss]').forEach(function (button) {
      button.addEventListener('click', closePicker);
    });
    root.querySelectorAll('[data-picker-genre]').forEach(function (button) {
      button.addEventListener('click', onPickerGenre);
    });
    document.addEventListener('keydown', onPickerKey);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', endDrag);
    if (form) {
      form.addEventListener('submit', rememberWeekScroll);
    }
  }

  function onPaletteClick(event) {
    if (ignoreClick) {
      return;
    }
    event.preventDefault();
    togglePalette(event.currentTarget.dataset.genre || '');
  }

  function onPalettePointerDown(event) {
    if (!isMousePointer(event)) {
      return;
    }
    const chip = event.currentTarget;
    startDrag(event, {
      kind: 'palette',
      genre: chip.dataset.genre || '',
      label: chip.dataset.label || '',
      tone: chip.dataset.genre || '',
    });
  }

  function onCellClick(event) {
    if (ignoreClick) {
      return;
    }
    if (event.target.closest('[data-clear-cell], [data-change-category]')) {
      return;
    }
    event.preventDefault();
    const cell = event.currentTarget;
    if (selectedGenre) {
      assignCell(cell, selectedGenre);
      submitRebuild(cell);
      return;
    }
    if (cellGenre(cell)) {
      submitRebuild(cell);
      return;
    }
    openPicker(cell);
  }

  function onChangeCategoryClick(event) {
    event.preventDefault();
    event.stopPropagation();
    const cell = event.currentTarget.closest('[data-drop-cell]');
    if (cell) {
      openPicker(cell);
    }
  }

  function onClearClick(event) {
    event.preventDefault();
    event.stopPropagation();
    const cell = event.currentTarget.closest('[data-drop-cell]');
    if (!cell) {
      return;
    }
    assignCell(cell, '');
    announce('Cleared ' + cellTitle(cell));
  }

  function onKindToggle(event) {
    const button = event.currentTarget;
    const day = button.dataset.day;
    const kind = button.dataset.kindToggle;
    const input = root.querySelector('select[name="day_kind_' + day + '"]');
    if (!input || !kind || input.value === kind) {
      return;
    }
    input.value = kind;
    submitWeekForm('day_kinds');
  }

  function togglePalette(genre) {
    selectedGenre = selectedGenre === genre ? '' : genre;
    root.querySelectorAll('[data-genre-chip]').forEach(function (chip) {
      chip.classList.toggle('is-selected', chip.dataset.genre === selectedGenre);
    });
    setHint(
      selectedGenre
        ? 'Selected: tap a slot to place it and pick a dish.'
        : defaultHint
    );
  }

  function openPicker(cell) {
    if (!picker) {
      return;
    }
    pickerCell = cell;
    if (pickerTitle) {
      pickerTitle.textContent = cellTitle(cell) || 'Choose a category';
    }
    const current = cellGenre(cell);
    root.querySelectorAll('[data-picker-genre]').forEach(function (button) {
      button.classList.toggle('is-selected', button.dataset.pickerGenre === current);
    });
    picker.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closePicker() {
    if (!picker) {
      return;
    }
    picker.hidden = true;
    pickerCell = null;
    document.body.style.overflow = '';
  }

  function onPickerGenre(event) {
    const cell = pickerCell;
    if (!cell) {
      return;
    }
    const genre = event.currentTarget.dataset.pickerGenre || '';
    assignCell(cell, genre);
    closePicker();
    if (genre) {
      submitRebuild(cell);
    }
  }

  function submitRebuild(cell) {
    if (!rebuildDayInput || !rebuildSlotInput) {
      return;
    }
    rebuildDayInput.value = cell.dataset.day || '';
    rebuildSlotInput.value = cell.dataset.slotId || '';
    submitWeekForm('rebuild_slot');
  }

  function submitWeekForm(formId) {
    if (!form || !formIdInput || !formId) {
      return;
    }
    rememberWeekScroll();
    formIdInput.value = formId;
    HTMLFormElement.prototype.submit.call(form);
  }

  function keepWeekScroll() {
    try {
      history.scrollRestoration = 'manual';
    } catch (ignore) {}
    restoreWeekScroll();
    if (document.readyState === 'complete') {
      window.setTimeout(forgetWeekScroll, 300);
      return;
    }
    window.addEventListener('load', function () {
      restoreWeekScroll();
      window.setTimeout(forgetWeekScroll, 300);
    });
  }

  function rememberWeekScroll() {
    try {
      sessionStorage.setItem(SCROLL_KEY, String(window.scrollY || window.pageYOffset || 0));
    } catch (ignore) {}
  }

  function restoreWeekScroll() {
    try {
      const raw = sessionStorage.getItem(SCROLL_KEY);
      if (raw === null) {
        return;
      }
      const y = Number(raw);
      if (Number.isFinite(y)) {
        window.scrollTo(0, y);
      }
    } catch (ignore) {}
  }

  function forgetWeekScroll() {
    try {
      sessionStorage.removeItem(SCROLL_KEY);
    } catch (ignore) {}
  }

  function onPickerKey(event) {
    if (event.key === 'Escape' && picker && !picker.hidden) {
      closePicker();
    }
  }

  function startDrag(event, payload) {
    if (!payload.genre) {
      return;
    }
    drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      ghost: null,
      target: null,
      ...payload,
    };
  }

  function onPointerMove(event) {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (!drag.moved && distance < DRAG_THRESHOLD) {
      return;
    }
    if (!drag.moved) {
      beginPointerDrag(event);
    }
    moveGhost(event.clientX, event.clientY);
    highlightCell(cellFromPoint(event.clientX, event.clientY));
  }

  function beginPointerDrag(event) {
    drag.moved = true;
    root.classList.add('is-dragging');
    document.body.style.userSelect = 'none';
    drag.ghost = document.createElement('div');
    drag.ghost.className = 'week-plan-ghost';
    drag.ghost.dataset.tone = drag.tone;
    drag.ghost.textContent = drag.label;
    document.body.appendChild(drag.ghost);
    try {
      event.target.setPointerCapture(event.pointerId);
    } catch (ignore) {
      /* Some browsers reject capture on window-level listeners. */
    }
  }

  function onPointerUp(event) {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    const active = drag;
    const target = active.moved ? cellFromPoint(event.clientX, event.clientY) : null;
    if (active.moved) {
      ignoreClick = true;
      window.setTimeout(function () {
        ignoreClick = false;
      }, 50);
    }
    endDrag();
    if (!active.moved || !target || !active.genre) {
      return;
    }
    assignCell(target, active.genre);
    submitRebuild(target);
  }

  function endDrag() {
    if (!drag) {
      return;
    }
    if (drag.ghost) {
      drag.ghost.remove();
    }
    highlightCell(null);
    root.classList.remove('is-dragging');
    document.body.style.userSelect = '';
    drag = null;
  }

  function assignCell(cell, genre) {
    const select = cell.querySelector('select');
    if (!select) {
      return;
    }
    select.value = genre;
    refreshCell(cell);
  }

  function refreshCell(cell) {
    const genre = cellGenre(cell);
    const original = cell.dataset.originalGenre || '';
    const mealName = cell.dataset.mealName || '';
    const hasMeal = Boolean(mealName && genre && genre === original);
    cell.toggleAttribute('data-empty', !genre);
    cell.toggleAttribute('data-has-meal', hasMeal);
    cell.toggleAttribute('data-pending', Boolean(genre && !hasMeal));
    paintFaceTone(cell, genre);
    paintFaceCopy(cell, genre, hasMeal, mealName);
  }

  function paintFaceTone(cell, genre) {
    const face = cell.querySelector('[data-face]');
    const emoji = cell.querySelector('[data-face-emoji]');
    if (face) {
      if (genre) {
        face.setAttribute('data-tone', genre);
      } else {
        face.removeAttribute('data-tone');
      }
    }
    if (emoji) {
      emoji.textContent = genreEmoji(genre);
    }
  }

  function paintFaceCopy(cell, genre, hasMeal, mealName) {
    const title = cell.querySelector('[data-face-title-text]');
    const chip = cell.querySelector('[data-face-chip]');
    const chipLabel = cell.querySelector('[data-face-chip-label]');
    const status = cell.querySelector('[data-face-status]');
    const kcal = cell.querySelector('[data-face-kcal]');
    const preview = cell.querySelector('[data-face-preview]');
    const genreLabel = genre ? cellLabel(cell) : '';
    if (title) {
      title.textContent = hasMeal ? mealName : genreLabel || 'Tap to choose a category';
    }
    if (chipLabel) {
      chipLabel.textContent = genreLabel;
    }
    if (chip) {
      chip.hidden = !hasMeal;
    }
    if (status) {
      status.hidden = hasMeal || !genre;
    }
    if (kcal) {
      kcal.hidden = !hasMeal;
      kcal.textContent = hasMeal && cell.dataset.mealKcal ? cell.dataset.mealKcal + ' kcal' : '';
    }
    if (preview) {
      preview.hidden = !hasMeal;
    }
  }

  function cellGenre(cell) {
    const select = cell.querySelector('select');
    return select ? select.value : '';
  }

  function cellLabel(cell) {
    const genre = cellGenre(cell);
    const chip = chipFor(genre);
    return chip ? chip.dataset.label || genre : genre;
  }

  function genreEmoji(genre) {
    const chip = chipFor(genre);
    return chip ? chip.dataset.emoji || '' : '';
  }

  function chipFor(genre) {
    if (!genre) {
      return null;
    }
    return root.querySelector('[data-genre-chip][data-genre="' + genre + '"]');
  }

  function cellTitle(cell) {
    const day = cell.closest('[data-day-card]');
    const slot = cell.querySelector('[data-face-slot]');
    const dayLabel = day ? day.dataset.dayLabel || '' : '';
    const slotLabel = slot ? slot.textContent.trim() : '';
    return (dayLabel + ' ' + slotLabel).trim();
  }

  function isMousePointer(event) {
    if (event.button && event.button !== 0) {
      return false;
    }
    return event.pointerType === 'mouse' || event.pointerType === 'pen';
  }

  function cellFromPoint(x, y) {
    const node = document.elementFromPoint(x, y);
    return node ? node.closest('[data-drop-cell]') : null;
  }

  function highlightCell(cell) {
    root.querySelectorAll('[data-drop-cell].is-drop-target').forEach(function (item) {
      item.classList.remove('is-drop-target');
    });
    if (cell) {
      cell.classList.add('is-drop-target');
    }
  }

  function moveGhost(x, y) {
    if (!drag || !drag.ghost) {
      return;
    }
    drag.ghost.style.left = x + 'px';
    drag.ghost.style.top = y + 'px';
  }

  function setHint(text) {
    if (hint) {
      hint.textContent = text;
    }
  }

  function announce(text) {
    if (live) {
      live.textContent = text;
    }
  }
})();
