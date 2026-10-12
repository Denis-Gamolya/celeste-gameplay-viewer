/* Test generated project UI in an isolated headless browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function checkPrototype() {
  const [htmlPath, playwrightModule = 'playwright', executablePath] = process.argv.slice(2);
  if (!htmlPath) throw Error('Provide the prototype index.html path.');
  const {chromium} = require(playwrightModule);
  const html = await fs.readFile(htmlPath, 'utf8');
  const manifest = JSON.parse(await fs.readFile(path.join(path.dirname(htmlPath), 'manifest.json'), 'utf8'));
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [];
  let requestCount = 0;
  let checked = 0;
  try {
    const context = await browser.newContext({viewport: {width: 1100, height: 900}});
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('request', () => requestCount++);
    await page.setContent(html);
    const map = page.frameLocator('[data-loenn-frame]');
    await map.locator('.ri').first().waitFor();
    await page.waitForFunction(() => document.querySelector('[data-loenn-frame]').contentWindow !== null);
    assert.equal(await map.locator('.ri').count(), manifest.room_count);

    for (const room of manifest.loenn_room_names) {
      await map.locator(`.ri[aria-label="Open ${room}"]`).click();
      await page.waitForFunction(name => document.querySelector('[data-room] option:checked').textContent === name, room);
      await page.locator('[data-preview]').evaluate(image => image.decode());
      assert.equal(await page.locator('[data-preview]').evaluate(image => image.naturalWidth), 1472);
      assert.equal(await page.evaluate(() => document.activeElement.hasAttribute('data-overview')), true);
      checked++;
      await page.locator('[data-overview]').click();
      await page.locator('[data-view="map"]').waitFor();
    }

    await map.locator('#btn-zi').click();
    await map.locator('#search').fill('s1');
    const before = await map.locator('#svg').getAttribute('style');
    await map.locator('.ri[aria-label="Open lvl_s1"]').click();
    await page.locator('[data-view="room"]').waitFor();
    await page.locator('[data-overview]').click();
    await page.locator('[data-view="map"]').waitFor();
    assert.equal(await map.locator('#svg').getAttribute('style'), before);
    assert.equal(await map.locator('#search').inputValue(), 's1');
    await map.locator('#search').fill('');
    await map.locator('#btn-fit').click();

    // Ignore messages sent by other windows, even if they copy the channel.
    await page.evaluate(() => {
      const frame = document.querySelector('[data-loenn-frame]');
      const channel = frame.srcdoc.match(/const channel = "([a-f0-9]+)"/)[1];
      window.dispatchEvent(new MessageEvent('message', {
        source: window, data: {type: 'celeste:open-room', channel, room: 'lvl_s1'},
      }));
    });
    assert.equal(await page.locator('[data-view]').getAttribute('data-view'), 'map');

    // Check the same local embedding under the MCP App's restrictive policy.
    const policy = '<meta http-equiv="Content-Security-Policy" content="' +
      "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
      "img-src data:; connect-src 'none'; frame-src 'none'\">";
    const strictPage = await context.newPage();
    strictPage.on('pageerror', error => errors.push(String(error)));
    await strictPage.setContent(html.replace('<style>', policy + '<style>'));
    const strictMap = strictPage.frameLocator('[data-loenn-frame]');
    await strictMap.locator('.ri[aria-label="Open lvl_7zb"]').click();
    await strictPage.waitForFunction(() => document.querySelector('[data-room] option:checked').textContent === 'lvl_7zb');
    await strictPage.locator('[data-preview]').evaluate(image => image.decode());
    await strictPage.close();

    const mobileContext = await browser.newContext({
      viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true,
    });
    const mobile = await mobileContext.newPage();
    mobile.on('pageerror', error => errors.push(String(error)));
    await mobile.setContent(html);
    await mobile.frameLocator('[data-loenn-frame]').locator('.ri[aria-label="Open lvl_12"]').tap();
    await mobile.waitForFunction(() => document.querySelector('[data-room] option:checked').textContent === 'lvl_12');
    await mobile.locator('[data-preview]').evaluate(image => image.decode());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await mobile.locator('[data-overview]').tap();
    await mobile.locator('[data-view="map"]').waitFor();
    assert.deepEqual(errors, []);
    assert.equal(requestCount, 0);
    console.log(JSON.stringify({rooms_clicked: checked, mobile_tap: 'passed', map_state: 'preserved', strict_csp: 'passed', requests: requestCount, errors}));
  } finally {
    await browser.close();
  }
}

checkPrototype().catch(error => { console.error(error); process.exitCode = 1; });
