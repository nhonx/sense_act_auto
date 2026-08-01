document.addEventListener('DOMContentLoaded', () => {
  const output = document.getElementById('output');

  async function sendToActiveTab(action, payload = {}) {
    output.textContent = `Sending ${action}...`;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      output.textContent = 'Error: No active tab found.';
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action, payload, requestId: Date.now().toString() }, (res) => {
      if (chrome.runtime.lastError) {
        output.textContent = `Error: ${chrome.runtime.lastError.message}`;
      } else {
        output.textContent = JSON.stringify(res, null, 2);
      }
    });
  }

  document.getElementById('btn-analyze').addEventListener('click', () => sendToActiveTab('analyze_site'));
  document.getElementById('btn-scan').addEventListener('click', () => sendToActiveTab('scan_page'));
  document.getElementById('btn-geometry').addEventListener('click', () => sendToActiveTab('get_geometry'));
  document.getElementById('btn-content').addEventListener('click', () => sendToActiveTab('extract_content'));
});
