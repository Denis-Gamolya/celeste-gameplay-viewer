/* Connect generated Loenn room targets to the enclosing room browser. */
(() => {
  const names = __ROOM_NAMES__;
  const channel = __CHANNEL__;
  const targets = document.getElementById('rooms');
  const viewport = document.getElementById('wrap');
  const pointers = new Map();
  let moved = false;

  viewport.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    if (pointers.size === 0) moved = false;
    pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    if (pointers.size > 1) moved = true;
  }, true);
  window.addEventListener('pointermove', event => {
    const start = pointers.get(event.pointerId);
    if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) >= 8) {
      moved = true;
    }
  }, true);
  window.addEventListener('pointerup', event => pointers.delete(event.pointerId), true);
  window.addEventListener('pointercancel', event => {
    moved = true;
    pointers.delete(event.pointerId);
  }, true);

  function openRoom(target) {
    const index = Number(target.dataset.idx);
    if (!Number.isInteger(index) || !names[index]) return;
    document.getElementById('tip').classList.remove('vis');
    window.parent.postMessage({type: 'celeste:open-room', channel, room: names[index]}, '*');
  }

  targets.addEventListener('click', event => {
    const target = event.target.closest('[data-idx]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (moved && event.detail !== 0) return;
    openRoom(target);
  }, true);
  targets.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const target = event.target.closest('[data-idx]');
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    openRoom(target);
  });
  for (const target of targets.querySelectorAll('[data-idx]')) {
    const name = names[Number(target.dataset.idx)];
    target.setAttribute('tabindex', '0');
    target.setAttribute('role', 'button');
    target.setAttribute('aria-label', `Open ${name}`);
  }
  // The room image takes the place of the upstream click-to-details panel.
  document.getElementById('btn-sb').click();
  document.getElementById('stats').textContent = `${names.length} rooms · scroll=zoom · drag=pan · click=room image`;
  const style = document.createElement('style');
  style.textContent = '#stats{color:#b7c1cd} #wrap{touch-action:none} #btn-sb{display:none} ' +
    '#title{min-width:0} #topbar{flex-wrap:wrap} .ri:focus{outline:3px solid #fff}';
  document.head.append(style);
})();
