import { useState } from 'react';
import './ChatPanel.css';

interface ChatMessage {
  role: 'assistant' | 'user';
  content: string;
  toolCalls?: { name: string; display: string }[];
  dataCards?: DataCard[];
  suggestedQueries?: string[];
}

interface DataCard {
  severity: 'high' | 'med' | 'low';
  title: string;
  icon: 'error' | 'warning';
  rows: { key: string; value: string; color?: string }[];
}

const initialMessages: ChatMessage[] = [
  {
    role: 'assistant',
    content: 'Good morning. I\'m monitoring all 9 essentials for <strong>18-Feb-2026</strong>. Here\'s a quick summary: 5 batches completed successfully, 2 are running (DERIVATIVES, COLLATERAL), 1 has failed (FR2052A), and UPC hasn\'t started yet.',
    suggestedQueries: ['What failed in FR2052A?', 'DERIVATIVES ETA?', 'Show AWS metrics'],
  },
  {
    role: 'user',
    content: 'What failed in FR2052A? Give me the RCA.',
  },
  {
    role: 'assistant',
    content: 'FR2052A (6G) PRELIM failed at <strong>sequence step 3</strong>. Let me pull the details.',
    toolCalls: [
      { name: 'resolve_batch', display: 'resolve_batch("FR2052A") \u2192 Lenz API' },
      { name: 'get_batch_status', display: 'get_batch_status(8 datasets, "2026-02-18", "PRELIM")' },
      { name: 'get_task_details', display: 'get_task_details("FGW_6g_calc_workflow_V2_2026-02-18_...")' },
    ],
    dataCards: [
      {
        severity: 'high',
        title: 'Failed DAG: 6g_calc_workflow_V2',
        icon: 'error',
        rows: [
          { key: 'Dataset', value: 'com.jpmc...6g_calc_results' },
          { key: 'Failed Task', value: 'enrich_6g_calc_results', color: 'var(--error)' },
          { key: 'Slice', value: '6G-GLOBAL-SLICE-2' },
          { key: 'Failed At', value: '08:15:44 UTC' },
          { key: 'Attempts', value: '2 / 2' },
        ],
      },
    ],
  },
];

const rcaFollowUp: ChatMessage = {
  role: 'assistant',
  content: 'The <code>enrich_6g_calc_results</code> task failed after 2 retries on the GLOBAL-SLICE-2 slice. Checking AWS metrics for the failure window (08:00\u201308:20)...',
  toolCalls: [
    { name: 'get_cloudwatch_metrics', display: 'get_cloudwatch_metrics("RDS", "ReadLatency", "08:00-08:20")' },
  ],
  dataCards: [
    {
      severity: 'med',
      title: 'AWS Metric Anomaly Detected',
      icon: 'warning',
      rows: [
        { key: 'RDS ReadLatency', value: '\u2191 340ms (avg: 12ms)', color: 'var(--error)' },
        { key: 'RDS CPU', value: '\u2191 89% (avg: 35%)', color: 'var(--warning)' },
        { key: 'SQS Age of Oldest', value: 'Normal (4s)', color: 'var(--success)' },
      ],
    },
  ],
  suggestedQueries: ['RDS metrics last 4 hours', 'Has this failed before?', 'Which batches depend on 6G?'],
};

export default function ChatPanel() {
  const [messages] = useState<ChatMessage[]>([
    ...initialMessages,
    rcaFollowUp,
  ]);

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-logo">S</div>
          <div>
            <div className="chat-title">SENTRY AI</div>
            <div className="chat-status">
              <span className="chat-status-dot" />
              Connected &middot; GPT-4o
            </div>
          </div>
        </div>
        <div className="chat-actions">
          <button className="chat-action-btn" title="New conversation">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          <button className="chat-action-btn" title="History">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
          </button>
          <button className="chat-action-btn" title="Expand">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
            </svg>
          </button>
        </div>
      </div>

      <div className="chat-context">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" /><circle cx="12" cy="10" r="3" />
        </svg>
        Context:
        <span className="context-tag">18-Feb-2026 <span className="remove">&times;</span></span>
        <span className="context-tag">PROD <span className="remove">&times;</span></span>
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`msg ${msg.role}`}>
            <div className="msg-label">{msg.role === 'assistant' ? 'SENTRY AI' : 'You'}</div>
            <div className="msg-bubble">
              <span dangerouslySetInnerHTML={{ __html: msg.content }} />

              {msg.toolCalls?.map((tc, j) => (
                <div key={j} className="tool-call">
                  <div className="tool-call-header">
                    <span className="tool-icon">&zwnj;&#9889;</span> {tc.display}
                  </div>
                </div>
              ))}

              {msg.dataCards?.map((card, j) => (
                <div key={j} className={`msg-data-card severity-${card.severity}`}>
                  <div className="msg-data-header">
                    {card.icon === 'error' ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--error)" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
                      </svg>
                    ) : (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--warning)" strokeWidth="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                    )}
                    {card.title}
                  </div>
                  {card.rows.map((row, k) => (
                    <div key={k} className="msg-data-row">
                      <span className="msg-data-key">{row.key}</span>
                      <span className="msg-data-val" style={row.color ? { color: row.color } : undefined}>
                        {row.value}
                      </span>
                    </div>
                  ))}
                </div>
              ))}

              {msg.suggestedQueries && (
                <div className="suggested-queries">
                  {msg.suggestedQueries.map((q, j) => (
                    <button key={j} className="suggested-chip">{q}</button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <textarea
            className="chat-input"
            rows={1}
            placeholder="Ask about batch status, RCA, metrics..."
          />
          <button className="chat-send-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <div className="chat-input-hint">
          <kbd>Enter</kbd> to send &middot; <kbd>Shift+Enter</kbd> for new line &middot; Tools: Lenz, RDS, Airflow, CloudWatch
        </div>
      </div>
    </div>
  );
}
