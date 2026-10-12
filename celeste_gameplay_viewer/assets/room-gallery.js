/* Shared browser controller; map data is supplied by the Python template. */
(() => {
  const root = document.getElementById('__INSTANCE__');
  const initialRooms = __ROOM_DATA__;
  let pages = [];
  let hasLocalSelection = false;
  const roomSelect = root.querySelector('[data-room]');
  const previousButton = root.querySelector('[data-previous]');
  const nextButton = root.querySelector('[data-next]');
  const previewImage = root.querySelector('[data-preview]');
  const status = root.querySelector('[data-status]');
  const overviewButton = root.querySelector('[data-overview]');
  const roomRegions = root.querySelector('[data-regions]');
  const viewport = root.querySelector('[data-viewport]');
  const stage = root.querySelector('[data-stage]');
  const zoomStatus = root.querySelector('[data-zoom-status]');
  const zoomIn = root.querySelector('[data-zoom-in]');
  const zoomOut = root.querySelector('[data-zoom-out]');
  const fitButton = root.querySelector('[data-fit]');
  const actualButton = root.querySelector('[data-actual]');
  let zoomScale = 1;
  let fitMode = true;
  let imageReady = false;
  let suppressClick = false;
  const activePointers = new Map();
  const fitScale = () => Math.min(1, viewport.clientWidth / previewImage.naturalWidth);

  function updateZoom() {
    if (!imageReady) return;
    stage.style.width = `${previewImage.naturalWidth * zoomScale}px`;
    previewImage.style.imageRendering = zoomScale >= 1 ? 'pixelated' : 'auto';
    const heightScale = fitMode ? fitScale() : Math.min(zoomScale, 1);
    viewport.style.height = `${Math.min(600, previewImage.naturalHeight * heightScale)}px`;
    zoomStatus.textContent = `${Math.round(zoomScale * 100)}% · ${previewImage.naturalWidth} px`;
    zoomOut.disabled = zoomScale <= fitScale() + 0.0001;
    zoomIn.disabled = zoomScale >= 4;
  }

  function zoomTo(value, anchorX = viewport.clientWidth / 2,
                  anchorY = viewport.clientHeight / 2) {
    if (!imageReady) return;
    const imageX = (viewport.scrollLeft + anchorX) / zoomScale;
    const imageY = (viewport.scrollTop + anchorY) / zoomScale;
    zoomScale = Math.max(fitScale(), Math.min(4, value));
    fitMode = false;
    updateZoom();
    viewport.scrollLeft = imageX * zoomScale - anchorX;
    viewport.scrollTop = imageY * zoomScale - anchorY;
  }

  function fitImage() {
    fitMode = true;
    if (!imageReady) return;
    zoomScale = fitScale();
    updateZoom();
    viewport.scrollLeft = viewport.scrollTop = 0;
  }

  previewImage.addEventListener('load', () => {
    imageReady = true;
    fitButton.disabled = actualButton.disabled = false;
    fitImage();
  });
  fitButton.addEventListener('click', fitImage);
  actualButton.addEventListener('click', () => zoomTo(1));
  zoomIn.addEventListener('click', () => zoomTo(zoomScale * 1.5));
  zoomOut.addEventListener('click', () => zoomTo(zoomScale / 1.5));
  new ResizeObserver(() => {
    if (fitMode) fitImage();
    else if (imageReady) {
      zoomScale = Math.max(zoomScale, fitScale());
      updateZoom();
    }
  }).observe(viewport);

  viewport.addEventListener('wheel', event => {
    if (!event.ctrlKey || !imageReady) return;
    event.preventDefault();
    const bounds = viewport.getBoundingClientRect();
    zoomTo(zoomScale * Math.exp(-event.deltaY * 0.01),
           event.clientX - bounds.left, event.clientY - bounds.top);
  }, {passive: false});

  viewport.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !imageReady) return;
    if (activePointers.size === 0) suppressClick = false;
    activePointers.set(event.pointerId, {
      x: event.clientX, y: event.clientY,
      startX: event.clientX, startY: event.clientY,
    });
  });

  viewport.addEventListener('pointermove', event => {
    const point = activePointers.get(event.pointerId);
    if (!point) return;
    const oldPoints = [...activePointers.values()].map(item => ({...item}));
    const dx = event.clientX - point.x;
    const dy = event.clientY - point.y;
    point.x = event.clientX;
    point.y = event.clientY;
    if (!suppressClick && activePointers.size < 2 &&
        Math.hypot(point.x - point.startX, point.y - point.startY) < 6) return;
    suppressClick = true;
    viewport.dataset.panning = '';
    // Capture only after a drag starts so ordinary room clicks keep their target.
    viewport.setPointerCapture(event.pointerId);
    if (activePointers.size === 2) {
      const [beforeA, beforeB] = oldPoints;
      const [afterA, afterB] = [...activePointers.values()];
      const oldDistance = Math.hypot(beforeA.x - beforeB.x, beforeA.y - beforeB.y);
      const newDistance = Math.hypot(afterA.x - afterB.x, afterA.y - afterB.y);
      const bounds = viewport.getBoundingClientRect();
      if (oldDistance > 0) {
        zoomTo(zoomScale * newDistance / oldDistance,
               (beforeA.x + beforeB.x) / 2 - bounds.left,
               (beforeA.y + beforeB.y) / 2 - bounds.top);
        viewport.scrollLeft -= dx / 2;
        viewport.scrollTop -= dy / 2;
      }
    } else {
      viewport.scrollLeft -= dx;
      viewport.scrollTop -= dy;
    }
  });

  function endPointer(event) {
    activePointers.delete(event.pointerId);
    if (activePointers.size === 0) delete viewport.dataset.panning;
  }
  window.addEventListener('pointerup', endPointer);
  window.addEventListener('pointercancel', endPointer);
  viewport.addEventListener('lostpointercapture', endPointer);
  viewport.addEventListener('click', event => {
    if (suppressClick && event.detail !== 0) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  function loadPages(newPages) {
    pages = newPages;
    hasLocalSelection = false;
    roomSelect.replaceChildren();
    roomRegions.replaceChildren();
    for (const [index, room] of pages.entries()) {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = room.name;
      roomSelect.append(option);
    }
    const roomPages = new Map(pages.map((room, index) => [room.name, index]));
    const overviewPage = pages[0] || {};
    // Smaller pages win overlaps; equal areas use their original map order.
    const area = region => (region.bounds[2] - region.bounds[0]) * (region.bounds[3] - region.bounds[1]);
    for (const region of [...(overviewPage.regions || [])].sort((a, b) => area(b) - area(a))) {
      const page = roomPages.get(region.room);
      if (!page || pages[page].kind !== 'room') continue;
      const [left, top, right, bottom] = region.bounds;
      const [width, height] = overviewPage.size;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cursor-interaction';
      button.dataset.region = region.room;
      button.setAttribute('aria-label', `Open ${region.room}`);
      button.setAttribute('data-tooltip', region.room);
      button.style.left = `${left / width * 100}%`;
      button.style.top = `${top / height * 100}%`;
      button.style.width = `${(right - left) / width * 100}%`;
      button.style.height = `${(bottom - top) / height * 100}%`;
      button.addEventListener('click', () => {
        showPage(page, true);
        // Keep focus on a visible control without opening a mobile roomSelect picker.
        overviewButton.focus({preventScroll: true});
      });
      roomRegions.append(button);
    }
  }
  let currentPageIndex = 0;
  function showPage(index, save = false) {
    const empty = pages.length === 0;
    roomSelect.disabled = empty;
    viewport.hidden = empty;
    imageReady = false;
    zoomIn.disabled = zoomOut.disabled = fitButton.disabled = actualButton.disabled = true;
    zoomStatus.textContent = '';
    if (empty) {
      overviewButton.disabled = previousButton.disabled = nextButton.disabled = true;
      status.textContent = 'Waiting for map preview…';
      return;
    }
    if (save) hasLocalSelection = true;
    currentPageIndex = Math.max(0, Math.min(pages.length - 1, index));
    const room = pages[currentPageIndex];
    roomSelect.value = String(currentPageIndex);
    stage.style.width = '100%';
    viewport.scrollLeft = viewport.scrollTop = 0;
    activePointers.clear();
    delete viewport.dataset.panning;
    previewImage.src = room.image;
    previewImage.alt = room.kind === 'overview' ? 'Whole-map layout' : `Gameplay layout of ${room.name}`;
    roomRegions.hidden = room.kind !== 'overview';
    overviewButton.disabled = currentPageIndex === 0;
    status.textContent = room.kind === 'overview' ? `Whole map · ${pages.length - 1} rooms` : `${currentPageIndex} / ${pages.length - 1} · ${room.name}`;
    previousButton.disabled = currentPageIndex === 0;
    nextButton.disabled = currentPageIndex === pages.length - 1;
    if (save && typeof window.openai?.setWidgetState === 'function') {
      // Persistence is optional; synchronous and asynchronous hosts both work.
      try {
        Promise.resolve(window.openai.setWidgetState({
          modelContent: {room: room.name}, privateContent: null,
        })).catch(() => {});
      } catch {
        // A host persistence failure must not interrupt local navigation.
      }
    }
  }
  roomSelect.addEventListener('change', () => showPage(Number(roomSelect.value), true));
  previousButton.addEventListener('click', () => showPage(currentPageIndex - 1, true));
  nextButton.addEventListener('click', () => showPage(currentPageIndex + 1, true));
  overviewButton.addEventListener('click', () => showPage(0, true));
  function restoreSavedPage(state) {
    // Host snapshots hydrate a new gallery, but may arrive after a newer click.
    // Once the user navigates, this gallery owns its selection until replaced.
    if (hasLocalSelection) return;
    const name = state?.modelContent?.room;
    const found = pages.findIndex(room => room.name === name);
    if (found >= 0) showPage(found);
  }
  loadPages(initialRooms);
  showPage(0);
  restoreSavedPage(window.openai?.widgetState);
  root.addEventListener('celeste:pages', event => {
    loadPages(event.detail);
    showPage(0);
    restoreSavedPage(window.openai?.widgetState);
  });
  window.addEventListener('openai:set_globals', event => {
    const state = event.detail?.globals?.widgetState;
    // Height, theme, and display updates are partial, not navigation requests.
    if (state !== undefined) restoreSavedPage(state);
  });
})();
