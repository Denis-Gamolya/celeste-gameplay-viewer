/* Browser regression: host snapshots must not undo a newer local selection. */
window.addEventListener('load', async () => {
  const select = document.querySelector('[data-room]');
  const image = document.querySelector('[data-preview]');
  const overview = document.querySelector('[data-overview]');
  const failures = [];
  const check = (condition, message) => {
    if (!condition) failures.push(message);
  };
  const selectedName = () => select.selectedOptions[0]?.textContent;
  const update = globals => window.dispatchEvent(new CustomEvent(
    'openai:set_globals', {detail: {globals}},
  ));
  const saved = room => ({modelContent: {room}, privateContent: null});
  const tick = () => new Promise(resolve => setTimeout(resolve, 20));

  check(selectedName() === 'lvl_12', 'Restore saved room on initial load');
  update({widgetState: saved('lvl_7zb')});
  check(selectedName() === 'lvl_7zb', 'Allow delayed initial hydration');
  const buttons = [...document.querySelectorAll('[data-region]')];
  for (const button of buttons) {
    overview.click();
    button.click();
    const room = button.dataset.region;
    check(selectedName() === room, `Click opens ${room}`);
    await image.decode();
    // Resize updates can carry a valid but older navigation snapshot.
    await tick();
    update({maxHeight: 500, widgetState: saved('Whole map')});
    check(selectedName() === room, `Resize snapshot preserves ${room}`);
    update({theme: 'dark'});
    update({widgetState: null});
    update({widgetState: saved('missing-room')});
    update({widgetState: saved('lvl_12')});
    check(selectedName() === room, `Delayed state preserves ${room}`);
    check(image.alt === `Gameplay layout of ${room}`, `Image stays on ${room}`);
    check(document.activeElement === overview, `Picker stays unfocused: ${room}`);
  }

  overview.click();
  check(selectedName() === 'Whole map', 'Explicit Whole map still works');
  select.value = '1';
  select.dispatchEvent(new Event('change'));
  document.querySelector('[data-next]').click();
  const latest = selectedName();
  update({widgetState: saved('Whole map')});
  update({widgetState: saved('lvl_1')});
  check(selectedName() === latest, 'Out-of-order echoes keep latest selection');
  document.querySelector('[data-previous]').click();
  check(select.value === '1', 'Previous still works');
  check(window.savedNavigation.modelContent.room === selectedName(),
        'Latest choice is persisted');

  overview.click();
  await image.decode();
  document.body.dataset.stateCheck = failures.length ? 'failed' : 'passed';
  document.body.dataset.roomsChecked = String(buttons.length);
  document.body.dataset.failures = JSON.stringify(failures);
});
