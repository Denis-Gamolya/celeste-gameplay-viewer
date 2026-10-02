/* MCP Apps transport; the room browser itself is shared with inline previews. */
(() => {
  const root = document.getElementById('celeste-mcp-app');
  const status = root.querySelector('[data-status]');
  let initialized = false;
  let latestResult = null;
  let lastHash = null;
  let lastHeight = 0;
  function reportSize() {
    if (!initialized) return;
    const height = Math.ceil(root.getBoundingClientRect().height + 32);
    if (height === lastHeight) return;
    lastHeight = height;
    window.parent.postMessage({jsonrpc: '2.0', method: 'ui/notifications/size-changed',
                               params: {height}}, '*');
  }
  new ResizeObserver(reportSize).observe(root);
  const initializeId = 'celeste-initialize';
  const timeout = setTimeout(() => {
    if (!initialized) fail('This client did not connect the viewer. Use the inline or standalone gallery.');
  }, 10000);

  function fail(message) {
    root.dispatchEvent(new CustomEvent('celeste:pages', {detail: []}));
    status.setAttribute('role', 'alert');
    status.textContent = message;
    lastHash = null;
  }

  function deliver(result) {
    if (!initialized) {
      latestResult = result;
      return;
    }
    if (result?.isError) {
      fail('The map preview could not be generated. Request it again.');
      return;
    }
    const payload = result?._meta?.celesteGallery;
    if (!payload) {
      fail('This result contains no room images. Use the inline or standalone gallery.');
      return;
    }
    const pages = payload.pages;
    const validImage = value => typeof value === 'string' && /^data:image\/(png|webp);base64,[A-Za-z0-9+/=]+$/.test(value);
    const positivePair = value => Array.isArray(value) && value.length === 2 && value.every(number => Number.isFinite(number) && number > 0);
    const validPages = Array.isArray(pages) && pages.length > 1 &&
      pages.every(page => page && typeof page.name === 'string' && validImage(page.image)) &&
      pages[0].kind === 'overview' && positivePair(pages[0].size) &&
      pages.slice(1).every(page => page.kind === 'room');
    if (payload.schema_version !== 1 || typeof payload.source_hash !== 'string' ||
        !/^[a-f0-9]{64}$/.test(payload.source_hash) || !validPages) {
      fail('The room preview data is invalid. Request a fresh preview.');
      return;
    }
    const names = new Set(pages.slice(1).map(page => page.name));
    const regions = pages[0].regions;
    if (names.size !== pages.length - 1 || !Array.isArray(regions) ||
        regions.length !== names.size || new Set(regions.map(region => region?.room)).size !== names.size ||
        !regions.every(region => region && names.has(region.room) && Array.isArray(region.bounds) &&
          region.bounds.length === 4 && region.bounds.every(Number.isFinite) &&
          region.bounds[0] >= 0 && region.bounds[1] >= 0 &&
          region.bounds[0] < region.bounds[2] && region.bounds[1] < region.bounds[3] &&
          region.bounds[2] <= pages[0].size[0] && region.bounds[3] <= pages[0].size[1])) {
      fail('Room navigation data is invalid. Request a fresh preview.');
      return;
    }
    // A repeated delivery must not reset the user's current room.
    if (lastHash === payload.source_hash) return;
    status.removeAttribute('role');
    root.dispatchEvent(new CustomEvent('celeste:pages', {detail: pages}));
    lastHash = payload.source_hash;
  }

  window.addEventListener('message', event => {
    if (event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== '2.0') return;
    if (message.id === initializeId && !initialized) {
      clearTimeout(timeout);
      if (message.error || message.result?.protocolVersion !== '2026-01-26') {
        fail('This client could not initialize the room viewer. Use the inline gallery.');
        return;
      }
      initialized = true;
      window.parent.postMessage({jsonrpc: '2.0', method: 'ui/notifications/initialized', params: {}}, '*');
      reportSize();
      if (latestResult) deliver(latestResult);
    } else if (message.method === 'ui/notifications/tool-result') {
      deliver(message.params);
    }
  });
  window.parent.postMessage({
    jsonrpc: '2.0', id: initializeId, method: 'ui/initialize',
    params: {appInfo: {name: 'celeste-room-browser', version: '1.0.0'},
             appCapabilities: {}, protocolVersion: '2026-01-26'},
  }, '*');
})();
