/* Run inside a generated gallery; results are exposed on the document body. */
window.addEventListener('load', async () => {
  document.body.dataset.zoomStep = 'started';
  const query = selector => document.querySelector(selector);
  const image = query('[data-preview]');
  const viewport = query('[data-viewport]');
  const select = query('[data-room]');
  const failures = [];
  const check = (value, message) => { if (!value) failures.push(message); };
  const ready = async () => {
    if (!image.complete) {
      await Promise.race([image.decode(), new Promise(resolve => setTimeout(resolve, 1500))]);
    }
    await new Promise(resolve => setTimeout(resolve, 0));
    check(image.complete && image.naturalWidth > 0, 'Image decoded');
  };
  const selectPage = async index => {
    select.value = String(index);
    select.dispatchEvent(new Event('change'));
    await ready();
  };
  try {
    await ready();
    const pageCount = select.options.length;
    for (let index = 0; index < pageCount; index++) {
      document.body.dataset.zoomStep = String(index);
      await selectPage(index);
      check(image.getBoundingClientRect().width <= viewport.clientWidth + 1,
            `Page ${index} fits initially`);
      query('[data-actual]').click();
      check(Math.abs(image.getBoundingClientRect().width - image.naturalWidth) < 1,
            `Page ${index} displays at native resolution`);
      const centerBefore = (viewport.scrollLeft + viewport.clientWidth / 2);
      query('[data-zoom-in]').click();
      const ratio = image.getBoundingClientRect().width / image.naturalWidth;
      const centerAfter = (viewport.scrollLeft + viewport.clientWidth / 2) / ratio;
      check(Math.abs(centerAfter - centerBefore) < 2, `Page ${index} zoom preserves center`);
      check(document.documentElement.scrollWidth <= innerWidth, `Page ${index} has no outer overflow`);
      query('[data-fit]').click();
      check(viewport.scrollLeft === 0 && viewport.scrollTop === 0, `Page ${index} fit resets pan`);
    }
    await selectPage(0);
    query('[data-actual]').click();
    const bounds = viewport.getBoundingClientRect();
    const widthBefore = image.getBoundingClientRect().width;
    viewport.dispatchEvent(new WheelEvent('wheel', {ctrlKey: true, deltaY: -20,
      clientX: bounds.left + 100, clientY: bounds.top + 100, bubbles: true, cancelable: true}));
    check(image.getBoundingClientRect().width > widthBefore, 'Control-wheel zooms');

    // Synthetic touch pointers verify pinch math. Real mouse capture is checked separately.
    const originalCapture = viewport.setPointerCapture;
    viewport.setPointerCapture = () => {};
    const pointer = (type, id, x, y) => viewport.dispatchEvent(new PointerEvent(type, {
      pointerId: id, pointerType: 'touch', button: 0,
      clientX: bounds.left + x, clientY: bounds.top + y, bubbles: true,
    }));
    const pinchWidth = image.getBoundingClientRect().width;
    pointer('pointerdown', 1, 100, 100);
    pointer('pointerdown', 2, 200, 100);
    pointer('pointermove', 2, 250, 100);
    check(image.getBoundingClientRect().width > pinchWidth, 'Pinch spreads to zoom');
    pointer('pointerup', 1, 100, 100);
    pointer('pointerup', 2, 250, 100);
    const room = query('[data-region]');
    room.dispatchEvent(new MouseEvent('click', {bubbles: true, detail: 1}));
    check(select.value === '0', 'Pinch does not accidentally open a room');
    pointer('pointerdown', 3, 100, 100);
    pointer('pointerup', 3, 100, 100);
    room.dispatchEvent(new MouseEvent('click', {bubbles: true, detail: 1}));
    check(select.value !== '0', 'Next ordinary tap opens a room');
    viewport.setPointerCapture = originalCapture;
    await ready();
    query('[data-actual]').click();
    document.body.dataset.zoomCheck = failures.length ? 'failed' : 'passed';
    document.body.dataset.pagesChecked = String(pageCount);
    document.body.dataset.failures = JSON.stringify(failures);
  } catch (error) {
    document.body.dataset.zoomCheck = 'error';
    document.body.dataset.failures = error.stack;
  }
});
