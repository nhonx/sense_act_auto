/**
 * Component ABC - Content Script (Read-Only Sensor)
 * 
 * STRICT RULES ENFORCED:
 * - NO element.click()
 * - NO element.focus()
 * - NO event dispatching (dispatchEvent, MouseEvent, KeyboardEvent, etc.)
 * - NO mutation of DOM or input values
 * 
 * Only reads DOM topology, geometry, and content.
 */

(function () {
  let elementMap = new Map();
  let elementIdCounter = 0;
  let mutationObserver = null;
  let wsConnection = null;

  // Helper: check if element is visible in the current viewport
  function isElementVisible(el) {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      return false;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;

    // Check if within viewport bounds
    const inViewport = (
      rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
      rect.bottom > 0 &&
      rect.left < (window.innerWidth || document.documentElement.clientWidth) &&
      rect.right > 0
    );

    return inViewport;
  }

  // Get readable text summary for an element
  function getElementText(el) {
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      return el.getAttribute('placeholder') || el.value || el.getAttribute('aria-label') || '';
    }
    if (el.tagName === 'IMG') {
      return el.getAttribute('alt') || el.getAttribute('aria-label') || '';
    }
    return (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
  }

  // Walk DOM and scan interactive/relevant elements
  function scanViewportElements(options = {}) {
    const includeOffscreen = options.includeOffscreen || false;
    elementMap.clear();
    elementIdCounter = 0;

    const selectors = [
      'button',
      'a[href]',
      'input',
      'textarea',
      'select',
      '[role="button"]',
      '[role="link"]',
      '[role="checkbox"]',
      '[role="textbox"]',
      '[contenteditable="true"]',
      'img[alt]',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p',
      '[data-interactive="true"]'
    ];

    const elements = document.querySelectorAll(selectors.join(', '));
    const resultList = [];

    elements.forEach((el) => {
      if (!includeOffscreen && !isElementVisible(el)) {
        return;
      }

      elementIdCounter++;
      const id = `el_${String(elementIdCounter).padStart(3, '0')}`;
      elementMap.set(id, el);

      const rect = el.getBoundingClientRect();
      const text = getElementText(el);

      resultList.push({
        id: id,
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type') || null,
        role: el.getAttribute('role') || null,
        text: text.slice(0, 200), // truncate very long text
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          top: Math.round(rect.top),
          left: Math.round(rect.left),
          bottom: Math.round(rect.bottom),
          right: Math.round(rect.right)
        }
      });
    });

    return resultList;
  }

  // Get viewport & screen geometry
  function getGeometry() {
    return {
      screenX: window.screenX,
      screenY: window.screenY,
      screenWidth: window.screen.width,
      screenHeight: window.screen.height,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      outerWidth: window.outerWidth,
      outerHeight: window.outerHeight,
      devicePixelRatio: window.devicePixelRatio || 1,
      scrollX: window.scrollX || window.pageXOffset,
      scrollY: window.scrollY || window.pageYOffset,
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight
    };
  }

  // Extract structured main text content (cleaned text/markdown-like)
  function extractMainContent() {
    // Attempt to locate main content area or fall back to body
    const mainEl = document.querySelector('main, [role="main"], #content, article') || document.body;
    if (!mainEl) return '';

    const clone = mainEl.cloneNode(true);
    // Remove scripts, styles, nav, headers, footers from clone
    const removeSelectors = ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'svg', 'noscript', '.ad', '.ads'];
    removeSelectors.forEach(sel => {
      clone.querySelectorAll(sel).forEach(n => n.remove());
    });

    const lines = [];
    function walk(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.trim();
        if (text) lines.push(text);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName.toLowerCase();
        if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tag)) {
          lines.push(`\n# ${node.textContent.trim()}\n`);
        } else if (tag === 'p' || tag === 'li' || tag === 'div') {
          for (let child of node.childNodes) walk(child);
          lines.push('\n');
        } else {
          for (let child of node.childNodes) walk(child);
        }
      }
    }

    walk(clone);
    return lines.join(' ').replace(/\n\s*\n/g, '\n\n').trim();
  }

  // Setup MutationObserver to notify orchestrator of new content
  function setupMutationObserver() {
    if (mutationObserver) mutationObserver.disconnect();

    let debounceTimer = null;
    mutationObserver = new MutationObserver((mutations) => {
      let addedNodesCount = 0;
      mutations.forEach(m => {
        addedNodesCount += m.addedNodes.length;
      });

      if (addedNodesCount > 0) {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          sendNotification('dom_changed', {
            addedNodes: addedNodesCount,
            timestamp: Date.now()
          });
        }, 300);
      }
    });

    mutationObserver.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  // Send message back to background or WebSocket
  function sendNotification(type, payload) {
    if (chrome.runtime && chrome.runtime.sendMessage) {
      chrome.runtime.sendMessage({
        type: type,
        payload: payload
      }).catch(() => {});
    }
  }

  // Helper: Find associated label text for an input element
  function getAssociatedLabel(el) {
    if (el.id) {
      const labelEl = document.querySelector(`label[for="${el.id}"]`);
      if (labelEl) return labelEl.innerText.trim();
    }
    const parentLabel = el.closest('label');
    if (parentLabel) {
      return parentLabel.innerText.replace(el.innerText || '', '').trim();
    }
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  }

  // Comprehensive Site Analysis for XYZ Automation Reference
  function analyzeSite() {
    const geometry = getGeometry();
    // Estimate browser header/tab/address bar height offset (default ~80px if outerHeight unavailable)
    const headerOffset = (geometry.outerHeight && geometry.innerHeight) 
      ? Math.max(0, geometry.outerHeight - geometry.innerHeight) 
      : 80;

    const hostname = window.location.hostname.replace(/[^a-z0-9]/gi, '_') || 'page';
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `site_analysis_${hostname}_${timestamp}.json`;

    // 1. Structure & Headings
    const headings = Array.from(document.querySelectorAll('h1, h2, h3')).map(h => ({
      level: h.tagName.toLowerCase(),
      text: h.innerText.trim(),
      top: Math.round(h.getBoundingClientRect().top)
    }));

    // 2. Input Elements Scan
    const inputSelectors = 'input, textarea, select, [role="textbox"], [contenteditable="true"]';
    const inputElements = document.querySelectorAll(inputSelectors);
    const inputsList = [];

    inputElements.forEach((el, index) => {
      if (!isElementVisible(el)) return;
      const rect = el.getBoundingClientRect();
      const centerX = Math.round(rect.left + rect.width / 2);
      const centerY = Math.round(rect.top + rect.height / 2);
      const screenX = Math.round(geometry.screenX + centerX);
      const screenY = Math.round(geometry.screenY + headerOffset + centerY);

      inputsList.push({
        id: `input_${String(index + 1).padStart(3, '0')}`,
        element_id: el.id || null,
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type') || (el.tagName.toLowerCase() === 'textarea' ? 'textarea' : 'text'),
        name: el.getAttribute('name') || null,
        placeholder: el.getAttribute('placeholder') || null,
        label: getAssociatedLabel(el),
        value: el.value || '',
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        },
        center_viewport: { x: centerX, y: centerY },
        xyz_screen_coords: { screen_x: screenX, screen_y: screenY }
      });
    });

    // 3. Button & Clickable Target Scan
    const buttonSelectors = 'button, input[type="submit"], input[type="button"], a[href], [role="button"], [role="link"]';
    const buttonElements = document.querySelectorAll(buttonSelectors);
    const buttonsList = [];

    buttonElements.forEach((el, index) => {
      if (!isElementVisible(el)) return;
      const rect = el.getBoundingClientRect();
      const text = getElementText(el);
      if (!text && !el.getAttribute('title') && !el.getAttribute('aria-label')) return;

      const centerX = Math.round(rect.left + rect.width / 2);
      const centerY = Math.round(rect.top + rect.height / 2);
      const screenX = Math.round(geometry.screenX + centerX);
      const screenY = Math.round(geometry.screenY + headerOffset + centerY);

      buttonsList.push({
        id: `btn_${String(index + 1).padStart(3, '0')}`,
        element_id: el.id || null,
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute('type') || null,
        role: el.getAttribute('role') || null,
        text: text.slice(0, 100),
        href: el.getAttribute('href') || null,
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        },
        center_viewport: { x: centerX, y: centerY },
        xyz_screen_coords: { screen_x: screenX, screen_y: screenY }
      });
    });

    // 4. Form Structure Scan
    const forms = Array.from(document.querySelectorAll('form')).map((form, idx) => ({
      id: form.id || `form_${idx + 1}`,
      action: form.getAttribute('action') || null,
      method: (form.getAttribute('method') || 'GET').toUpperCase(),
      input_count: form.querySelectorAll(inputSelectors).length,
      button_count: form.querySelectorAll(buttonSelectors).length
    }));

    // Construct final JSON analysis report
    const analysisReport = {
      meta: {
        url: window.location.href,
        origin: window.location.origin,
        title: document.title,
        scanned_at: new Date().toISOString(),
        filename: filename
      },
      screen: {
        width: window.screen.width,
        height: window.screen.height,
        availWidth: window.screen.availWidth,
        availHeight: window.screen.availHeight,
        screenX: geometry.screenX,
        screenY: geometry.screenY,
        devicePixelRatio: geometry.devicePixelRatio
      },
      viewport: {
        innerWidth: geometry.innerWidth,
        innerHeight: geometry.innerHeight,
        outerWidth: geometry.outerWidth,
        outerHeight: geometry.outerHeight,
        headerOffsetEstimate: headerOffset,
        scrollX: geometry.scrollX,
        scrollY: geometry.scrollY,
        documentWidth: geometry.documentWidth,
        documentHeight: geometry.documentHeight
      },
      summary: {
        heading_count: headings.length,
        input_count: inputsList.length,
        button_count: buttonsList.length,
        form_count: forms.length
      },
      structure: {
        headings: headings,
        forms: forms
      },
      xyz_automation_targets: {
        inputs: inputsList,
        buttons: buttonsList
      }
    };

    // Automatically trigger JSON file download in browser
    try {
      const jsonStr = JSON.stringify(analysisReport, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      console.log(`[Component ABC] Exported site analysis JSON to ${filename}`);
    } catch (err) {
      console.error('[Component ABC] Error downloading JSON file:', err);
    }

    return analysisReport;
  }

  // Message listener for requests from background worker / orchestrator bridge
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    const { action, payload, requestId } = request;

    if (action === 'analyze_site') {
      const report = analyzeSite();
      sendResponse({ requestId, report, success: true });
    } else if (action === 'scan_page') {
      const elements = scanViewportElements(payload || {});
      const geometry = getGeometry();
      sendResponse({ requestId, elements, geometry, success: true });
    } else if (action === 'extract_content') {
      const content = extractMainContent();
      sendResponse({ requestId, content, success: true });
    } else if (action === 'get_geometry') {
      const geometry = getGeometry();
      sendResponse({ requestId, geometry, success: true });
    } else if (action === 'ping') {
      sendResponse({ status: 'alive', url: window.location.href, title: document.title });
    }

    return true; // Keep message channel open for async response
  });


  // Initialize observer
  if (document.body) {
    setupMutationObserver();
  } else {
    document.addEventListener('DOMContentLoaded', setupMutationObserver);
  }

  console.log('[Component ABC] Read-only Sensor content script loaded.');
})();
