/**
 * Component ABC - Background Service Worker
 * Manages active tab state and connects content script to Orchestrator via WebSocket bridge if needed.
 */

let socket = null;
const WS_URL = 'ws://localhost:8000/ws';

function connectWebSocket() {
  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.log('[Component ABC Background] Connected to Orchestrator WebSocket server');
      socket.send(JSON.stringify({ type: 'register', client: 'component_abc' }));
    };

    socket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[Component ABC Background] Received command from Orchestrator:', data);

        const { requestId, action, payload } = data;

        // Query active tab
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.id) {
          socket.send(JSON.stringify({ requestId, success: false, error: 'No active tab found' }));
          return;
        }

        // Forward message to content script in active tab
        chrome.tabs.sendMessage(tab.id, { action, payload, requestId }, (response) => {
          if (chrome.runtime.lastError) {
            socket.send(JSON.stringify({ requestId, success: false, error: chrome.runtime.lastError.message }));
          } else {
            socket.send(JSON.stringify({ requestId, success: true, ...response }));
          }
        });

      } catch (err) {
        console.error('[Component ABC Background] Error handling WebSocket message:', err);
      }
    };

    socket.onclose = () => {
      console.log('[Component ABC Background] WebSocket disconnected. Retrying in 3 seconds...');
      setTimeout(connectWebSocket, 3000);
    };

    socket.onerror = (err) => {
      console.error('[Component ABC Background] WebSocket error:', err);
      socket.close();
    };
  } catch (err) {
    console.error('[Component ABC Background] Connection attempt failed:', err);
    setTimeout(connectWebSocket, 3000);
  }
}

// Relays notifications from content.js to WebSocket if connected
chrome.runtime.onMessage.addListener((message, sender) => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      type: 'notification',
      tabId: sender.tab ? sender.tab.id : null,
      ...message
    }));
  }
});

// Auto connect on startup
connectWebSocket();
