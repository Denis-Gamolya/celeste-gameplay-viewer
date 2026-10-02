/* Browser regression: host layout updates must not navigate the gallery. */
window.addEventListener('load', async () => {
  const select = document.querySelector('[data-room]');
  const image = document.querySelector('[data-preview]');
  const overview = document.querySelector('[data-overview]');
  const checks = [];
  const check = (name, passed) => checks.push({name, passed});
  const update = globals => window.dispatchEvent(new CustomEvent(
    'openai:set_globals', {detail: {globals}}
  ));
  const selected = () => select.selectedOptions[0]?.textContent;
  const buttons = [...document.querySelectorAll('[data-region]')];
  const reported = ['lvl_s1', 'lvl_12', 'lvl_7zb'];
  buttons.sort((left, right) =>
    Number(reported.includes(right.dataset.region)) -
    Number(reported.includes(left.dataset.region))
  );
  try {
    for (const mode of ['promise', 'sync', 'reject', 'throw', 'absent']) {
      window.testSaveMode = mode;
      if (mode === 'absent') delete window.openai.setWidgetState;
      else window.openai.setWidgetState = window.testSaveState;
      for (const button of buttons) {
        overview.click();
        await image.decode();
        button.click();
        await image.decode();
        const name = button.dataset.region;
        check(`${mode}: open ${name}`, selected() === name);
        check(`${mode}: focus ${name}`, document.activeElement === overview);
        for (const globals of [
          {maxHeight: 500}, {theme: 'dark'}, {displayMode: 'inline'},
          {widgetState: undefined}, {widgetState: null},
          {widgetState: {modelContent: {room: 'missing-room'}}},
        ]) {
          update(globals);
          await Promise.resolve();
          check(`${mode}: retain ${name} after ${Object.keys(globals)[0]}`,
                selected() === name && image.alt.endsWith(name));
        }
      }
    }
    window.openai.setWidgetState = window.testSaveState;
    window.testSaveMode = 'sync';
    update({widgetState: {modelContent: {room: 'lvl_12'}}});
    check('Explicit saved room restores', selected() === 'lvl_12');
    update({widgetState: {modelContent: {room: 'Whole map'}}});
    check('Explicit overview restores', select.value === '0');
    document.querySelector('[data-next]').click();
    check('Next works', select.value === '1');
    document.querySelector('[data-previous]').click();
    check('Previous works', select.value === '0');
    select.value = '3';
    select.dispatchEvent(new Event('change'));
    check('Picker works', image.alt.endsWith(selected()));
    overview.click();
    check('Whole map works', select.value === '0');
    await new Promise(resolve => setTimeout(resolve, 50));
    check('No uncaught errors', window.testErrors.length === 0);
  } catch (error) {
    check(error.message, false);
  }
  const failed = checks.filter(item => !item.passed);
  const result = document.createElement('pre');
  result.id = 'regression-result';
  result.textContent = JSON.stringify({checks: checks.length, failures: failed.length,
    firstFailures: failed.slice(0, 12), errors: window.testErrors.slice(0, 4)}, null, 2);
  document.body.prepend(result);
  document.body.dataset.stateCheck = failed.length ? 'failed' : 'passed';
});
