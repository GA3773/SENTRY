/* ==========================================================================
   SENTRY — Chat Panel Logic
   Structure only in this session. Full wiring (SSE, send flow) in Session 7.
   ========================================================================== */

// ===== CHAT STATE =====
var chatState = {
  currentThreadId: generateUUID(),
  messages: [],
  isStreaming: false,
  activeBusinessDate: null,
  activeProcessingType: null,
};

// ===== RENDER FUNCTIONS =====

function renderUserMessage(text) {
  var container = document.getElementById('chatMessages');
  if (!container) return;

  var msg = document.createElement('div');
  msg.className = 'msg user';
  msg.innerHTML =
    '<div class="msg-label">You</div>' +
    '<div class="msg-bubble">' + escapeHtml(text) + '</div>';
  container.appendChild(msg);
  scrollChatToBottom();
}

function renderAssistantMessage(data) {
  var container = document.getElementById('chatMessages');
  if (!container) return;

  var msg = document.createElement('div');
  msg.className = 'msg assistant';

  var bubbleContent = '';

  // Tool calls
  if (data.tool_calls && data.tool_calls.length > 0) {
    data.tool_calls.forEach(function (tc) {
      bubbleContent += renderToolCallCard(tc);
    });
  }

  // Main text
  bubbleContent += data.text || '';

  // Structured data card
  if (data.structured_data) {
    bubbleContent += renderDataCard(data.structured_data);
  }

  // Suggested queries
  if (data.suggested_queries && data.suggested_queries.length > 0) {
    bubbleContent += '<div class="suggested-queries">';
    data.suggested_queries.forEach(function (q) {
      bubbleContent += '<button class="suggested-chip" onclick="sendChatMessage(\'' + escapeAttr(q) + '\')">' + escapeHtml(q) + '</button>';
    });
    bubbleContent += '</div>';
  }

  msg.innerHTML =
    '<div class="msg-label">SENTRY AI</div>' +
    '<div class="msg-bubble">' + bubbleContent + '</div>';
  container.appendChild(msg);
  scrollChatToBottom();
}

function renderToolCallCard(tc) {
  var name = tc.tool || 'unknown';
  var duration = tc.duration_ms ? ' (' + tc.duration_ms + 'ms)' : '';
  return (
    '<div class="tool-call">' +
    '<div class="tool-call-header">' +
    '<span class="tool-icon">\u26A1</span> ' + escapeHtml(name) + duration +
    '</div></div>'
  );
}

function renderDataCard(data) {
  if (!data || data.type === 'text_only') return '';

  var severity = '';
  if (data.failures && data.failures.length > 0) severity = ' severity-high';
  else if (data.summary && data.summary.running > 0) severity = ' severity-low';

  var html = '<div class="msg-data-card' + severity + '">';
  html += '<div class="msg-data-header">' + escapeHtml(data.batch_name || data.type || 'Data') + '</div>';

  if (data.summary) {
    var s = data.summary;
    html += renderDataRow('Total', s.total_datasets || s.total);
    html += renderDataRow('Success', s.success);
    html += renderDataRow('Failed', s.failed);
    html += renderDataRow('Running', s.running);
  }

  html += '</div>';
  return html;
}

function renderDataRow(key, val) {
  return (
    '<div class="msg-data-row">' +
    '<span class="msg-data-key">' + escapeHtml(key) + '</span>' +
    '<span class="msg-data-val">' + escapeHtml(String(val)) + '</span>' +
    '</div>'
  );
}

function renderThinkingIndicator(statusText) {
  removeThinkingIndicator();

  var container = document.getElementById('chatMessages');
  if (!container) return;

  var el = document.createElement('div');
  el.className = 'thinking-indicator';
  el.id = 'thinkingIndicator';
  el.innerHTML =
    '<div class="thinking-dots"><span></span><span></span><span></span></div>' +
    '<span id="thinkingStatus">' + (statusText || 'Thinking...') + '</span>';
  container.appendChild(el);
  scrollChatToBottom();
}

function updateThinkingStatus(text) {
  var status = document.getElementById('thinkingStatus');
  if (status) status.textContent = text;
}

function removeThinkingIndicator() {
  var el = document.getElementById('thinkingIndicator');
  if (el) el.remove();
}

// ===== SEND MESSAGE =====

function sendChatMessage(text) {
  if (!text) {
    var input = document.getElementById('chatInput');
    if (!input) return;
    text = input.value.trim();
    if (!text) return;
    input.value = '';
  }

  // Sync context from dashboard
  chatState.activeBusinessDate = typeof currentBusinessDate !== 'undefined' ? currentBusinessDate : null;
  chatState.activeProcessingType = typeof currentProcessingType !== 'undefined' ? currentProcessingType : null;

  renderUserMessage(text);
  renderThinkingIndicator('Processing...');
  chatState.isStreaming = true;

  var body = {
    message: text,
    thread_id: chatState.currentThreadId,
  };
  if (chatState.activeBusinessDate) body.business_date = chatState.activeBusinessDate;
  if (chatState.activeProcessingType && chatState.activeProcessingType !== 'ALL') {
    body.processing_type = chatState.activeProcessingType;
  }

  // Try SSE streaming first, fall back to regular POST
  streamChatResponse(body)
    .catch(function () {
      return postChatMessage(body);
    })
    .catch(function (err) {
      removeThinkingIndicator();
      chatState.isStreaming = false;
      renderAssistantMessage({
        text: 'Sorry, I encountered an error: ' + err.message,
        error: true,
      });
    });
}

// ===== SSE STREAMING =====

function streamChatResponse(body) {
  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(function (res) {
    if (!res.ok) throw new Error('HTTP ' + res.status);

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    function processChunk() {
      return reader.read().then(function (result) {
        if (result.done) {
          removeThinkingIndicator();
          chatState.isStreaming = false;
          return;
        }

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer

        lines.forEach(function (line) {
          line = line.trim();
          if (!line.startsWith('data:')) return;
          var payload = line.substring(5).trim();

          if (payload === '[DONE]') {
            removeThinkingIndicator();
            chatState.isStreaming = false;
            return;
          }

          try {
            var evt = JSON.parse(payload);
            handleSSEEvent(evt);
          } catch (e) {
            // Skip malformed events
          }
        });

        return processChunk();
      });
    }

    return processChunk();
  });
}

function handleSSEEvent(evt) {
  switch (evt.type) {
    case 'node_start':
      var nodeLabels = {
        context_loader: 'Loading context...',
        intent_classifier: 'Classifying intent...',
        batch_resolver: 'Resolving batch...',
        data_fetcher: 'Querying databases...',
        analyzer: 'Analyzing results...',
        response_synthesizer: 'Generating response...',
      };
      updateThinkingStatus(nodeLabels[evt.node] || 'Processing ' + evt.node + '...');
      break;

    case 'node_end':
      if (evt.node === 'batch_resolver' && evt.result && evt.result.dataset_count) {
        updateThinkingStatus('Found ' + evt.result.dataset_count + ' datasets...');
      }
      break;

    case 'tool_call':
      // Could append a tool call card in real-time
      break;

    case 'response':
      removeThinkingIndicator();
      chatState.isStreaming = false;
      if (evt.data) {
        renderAssistantMessage(evt.data);
      }
      break;
  }
}

// ===== REGULAR POST FALLBACK =====

function postChatMessage(body) {
  return fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      removeThinkingIndicator();
      chatState.isStreaming = false;
      if (data.response) {
        renderAssistantMessage(data.response);
      }
    });
}

// ===== HELPERS =====

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/'/g, '&#39;');
}

function scrollChatToBottom() {
  var container = document.getElementById('chatMessages');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

// ===== EVENT HANDLERS =====

document.addEventListener('DOMContentLoaded', function () {
  var input = document.getElementById('chatInput');
  var sendBtn = document.getElementById('chatSendBtn');
  var newChatBtn = document.getElementById('newChatBtn');

  // Send on Enter (Shift+Enter = new line)
  if (input) {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!chatState.isStreaming) {
          sendChatMessage();
        }
      }
    });
  }

  // Send button click
  if (sendBtn) {
    sendBtn.addEventListener('click', function () {
      if (!chatState.isStreaming) {
        sendChatMessage();
      }
    });
  }

  // New conversation button
  if (newChatBtn) {
    newChatBtn.addEventListener('click', function () {
      chatState.currentThreadId = generateUUID();
      chatState.messages = [];
      var container = document.getElementById('chatMessages');
      if (container) container.innerHTML = '';
    });
  }

  // Render welcome message
  renderAssistantMessage({
    text: 'Hello! I\'m SENTRY AI. Ask me about batch status, failures, RCA, or any essential. I can query Lenz, RDS, and Airflow to get real-time answers.',
    suggested_queries: [
      'How is derivatives doing today?',
      'What failed in FR2052A?',
      'Show me SNU status',
    ],
  });
});
