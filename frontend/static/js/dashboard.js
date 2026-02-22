/* ==========================================================================
   SENTRY — Dashboard Logic
   Fetches /api/essentials, renders table rows, expand/collapse, toggles, refresh.
   ========================================================================== */

// ===== STATE =====
var currentProcessingType = 'PRELIM';
var expandedEssential = null;
var currentBusinessDate = todayISO();
var autoRefreshInterval = null;
var AUTO_REFRESH_MS = 60000;

// ===== SVG CONSTANTS =====
var CHEVRON_SVG =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>';

// ===== MOCK DATA — matches GET /api/essentials response shape exactly =====
var MOCK_DATA = {
  business_date: '2026-02-18',
  timestamp: '2026-02-18T12:10:00Z',
  summary: { total: 9, completed: 5, running: 2, failed: 1, not_started: 1 },
  essentials: [
    {
      essential_name: 'TB-Derivatives',
      display_name: 'DERIVATIVES',
      status: 'RUNNING',
      prelim: {
        status: 'SUCCESS', total_datasets: 6, success: 6, failed: 0,
        running: 0, not_started: 0, progress: '6/6',
        started_at: '2026-02-18T05:20:39Z', last_updated: '2026-02-18T12:08:09Z', eta: null,
      },
      final: {
        status: 'RUNNING', total_datasets: 6, success: 4, failed: 0,
        running: 1, not_started: 1, progress: '4/6',
        started_at: '2026-02-18T05:20:39Z', last_updated: '2026-02-18T12:08:09Z', eta: '~14:30',
      },
      datasets: [
        { dataset_id: 'com.jpmc.ct.lri.derivatives-pb_synthetics_trs_e15', sequence_order: 0, prelim_status: 'SUCCESS', final_status: 'SUCCESS', slice_count: 8, slices_success: 8, slices_failed: 0, latest_dag_run_id: 'FGW_pb_synthetics_trs_e15_V2_2026-02-18_DERIV-NA-SLICE-1_1771403209811', duration_minutes: 102, created_date: '2026-02-18T05:20:00Z', updated_date: '2026-02-18T07:02:00Z' },
        { dataset_id: 'com.jpmc.ct.lri.derivatives-slsline_calculator_e15', sequence_order: 0, prelim_status: 'SUCCESS', final_status: 'SUCCESS', slice_count: 10, slices_success: 10, slices_failed: 0, latest_dag_run_id: 'FGW_slsline_calculator_e15_V2_2026-02-18_DERIV-EMEA-SLICE-1_1771403209812', duration_minutes: 131, created_date: '2026-02-18T05:23:00Z', updated_date: '2026-02-18T07:34:00Z' },
        { dataset_id: 'com.jpmc.ct.lri.derivatives-calc_intercompany_fx_adj_e15', sequence_order: 1, prelim_status: 'SUCCESS', final_status: 'SUCCESS', slice_count: 4, slices_success: 4, slices_failed: 0, latest_dag_run_id: 'FGW_calc_intercompany_fx_V2_2026-02-18_GLOBAL_1771403209813', duration_minutes: 45, created_date: '2026-02-18T07:35:00Z', updated_date: '2026-02-18T08:20:00Z' },
        { dataset_id: 'com.jpmc.ct.lri.derivatives-calc_secured_vs_unsecured_e15', sequence_order: 2, prelim_status: 'SUCCESS', final_status: 'SUCCESS', slice_count: 3, slices_success: 3, slices_failed: 0, latest_dag_run_id: 'FGW_calc_secured_unsecured_V2_2026-02-18_GLOBAL_1771403209814', duration_minutes: 38, created_date: '2026-02-18T08:22:00Z', updated_date: '2026-02-18T09:00:00Z' },
        { dataset_id: 'com.jpmc.ct.lri.cfg-contractual_cash_flow_results_v1', sequence_order: 3, prelim_status: 'SUCCESS', final_status: 'RUNNING', slice_count: 6, slices_success: 3, slices_failed: 0, latest_dag_run_id: 'FGW_contractual_cf_V2_2026-02-18_CFG-SLICE-1_1771403209815', duration_minutes: 185, created_date: '2026-02-18T09:04:00Z', updated_date: '2026-02-18T12:09:00Z' },
        { dataset_id: 'com.jpmc.ct.lri.sls-sls_aws_details_extended_v1', sequence_order: 4, prelim_status: 'SUCCESS', final_status: 'NOT_STARTED', slice_count: 0, slices_success: 0, slices_failed: 0, latest_dag_run_id: '', duration_minutes: 0, created_date: null, updated_date: null },
      ],
    },
    {
      essential_name: 'TB-Securities', display_name: 'SECURITIES', status: 'SUCCESS',
      prelim: { status: 'SUCCESS', total_datasets: 8, success: 8, failed: 0, running: 0, not_started: 0, progress: '8/8', started_at: '2026-02-18T04:15:22Z', last_updated: '2026-02-18T11:42:18Z', eta: null },
      final: { status: 'SUCCESS', total_datasets: 8, success: 8, failed: 0, running: 0, not_started: 0, progress: '8/8', started_at: '2026-02-18T04:15:22Z', last_updated: '2026-02-18T11:42:18Z', eta: null },
      datasets: [],
    },
    {
      essential_name: '6G-FR2052a-E2E', display_name: 'FR2052A (6G)', status: 'FAILED',
      prelim: { status: 'FAILED', total_datasets: 8, success: 3, failed: 1, running: 0, not_started: 4, progress: '3/8', started_at: '2026-02-18T04:30:10Z', last_updated: '2026-02-18T08:15:44Z', eta: null },
      final: { status: 'NOT_STARTED', total_datasets: 8, success: 0, failed: 0, running: 0, not_started: 8, progress: '0/8', started_at: null, last_updated: null, eta: null },
      datasets: [],
    },
    {
      essential_name: 'PBSynthetics', display_name: 'PBSynthetics', status: 'SUCCESS',
      prelim: { status: 'SUCCESS', total_datasets: 5, success: 5, failed: 0, running: 0, not_started: 0, progress: '5/5', started_at: '2026-02-18T05:00:15Z', last_updated: '2026-02-18T10:28:33Z', eta: null },
      final: { status: 'SUCCESS', total_datasets: 5, success: 5, failed: 0, running: 0, not_started: 0, progress: '5/5', started_at: '2026-02-18T05:00:15Z', last_updated: '2026-02-18T10:28:33Z', eta: null },
      datasets: [],
    },
    {
      essential_name: 'SNU', display_name: 'SNU', status: 'SUCCESS',
      prelim: { status: 'SUCCESS', total_datasets: 22, success: 22, failed: 0, running: 0, not_started: 0, progress: '22/22', started_at: '2026-02-18T05:20:39Z', last_updated: '2026-02-18T12:09:38Z', eta: null },
      final: { status: 'SUCCESS', total_datasets: 22, success: 22, failed: 0, running: 0, not_started: 0, progress: '22/22', started_at: '2026-02-18T05:20:39Z', last_updated: '2026-02-18T12:09:38Z', eta: null },
      datasets: [],
    },
    {
      essential_name: 'TB-Collateral', display_name: 'COLLATERAL', status: 'RUNNING',
      prelim: { status: 'SUCCESS', total_datasets: 11, success: 11, failed: 0, running: 0, not_started: 0, progress: '11/11', started_at: '2026-02-18T04:45:11Z', last_updated: '2026-02-18T12:05:22Z', eta: null },
      final: { status: 'RUNNING', total_datasets: 11, success: 9, failed: 0, running: 2, not_started: 0, progress: '9/11', started_at: '2026-02-18T04:45:11Z', last_updated: '2026-02-18T12:05:22Z', eta: '~13:15' },
      datasets: [],
    },
    {
      essential_name: 'TB-SMAA', display_name: 'SMAA', status: 'SUCCESS',
      prelim: { status: 'SUCCESS', total_datasets: 4, success: 4, failed: 0, running: 0, not_started: 0, progress: '4/4', started_at: '2026-02-18T04:50:08Z', last_updated: '2026-02-18T09:33:17Z', eta: null },
      final: { status: 'SUCCESS', total_datasets: 4, success: 4, failed: 0, running: 0, not_started: 0, progress: '4/4', started_at: '2026-02-18T04:50:08Z', last_updated: '2026-02-18T09:33:17Z', eta: null },
      datasets: [],
    },
    {
      essential_name: 'TB-SecFIn', display_name: 'SECFIN', status: 'SUCCESS',
      prelim: { status: 'SUCCESS', total_datasets: 7, success: 7, failed: 0, running: 0, not_started: 0, progress: '7/7', started_at: '2026-02-18T05:10:45Z', last_updated: '2026-02-18T11:15:09Z', eta: null },
      final: { status: 'SUCCESS', total_datasets: 7, success: 7, failed: 0, running: 0, not_started: 0, progress: '7/7', started_at: '2026-02-18T05:10:45Z', last_updated: '2026-02-18T11:15:09Z', eta: null },
      datasets: [],
    },
    {
      essential_name: 'UPC', display_name: 'UPC', status: 'WAITING',
      prelim: { status: 'NOT_STARTED', total_datasets: 6, success: 0, failed: 0, running: 0, not_started: 6, progress: '0/6', started_at: null, last_updated: null, eta: '~16:00' },
      final: { status: 'NOT_STARTED', total_datasets: 6, success: 0, failed: 0, running: 0, not_started: 6, progress: '0/6', started_at: null, last_updated: null, eta: null },
      datasets: [],
    },
  ],
};

// ===== HELPERS =====

function statusBadgeClass(s) {
  s = (s || '').toUpperCase();
  if (s === 'SUCCESS') return 'success';
  if (s === 'FAILED' || s === 'PARTIAL_FAILURE') return 'failed';
  if (s === 'RUNNING') return 'running';
  if (s === 'WAITING' || s === 'NOT_STARTED') return 'warning';
  return 'cancelled';
}

function statusLabel(s) {
  s = (s || '').toUpperCase();
  if (s === 'NOT_STARTED') return 'PENDING';
  if (s === 'PARTIAL_FAILURE') return 'FAILED';
  return s;
}

function procDotClass(s) {
  s = (s || '').toUpperCase();
  if (s === 'SUCCESS') return 'green';
  if (s === 'FAILED' || s === 'PARTIAL_FAILURE') return 'red';
  if (s === 'RUNNING') return 'blue';
  if (s === 'WAITING') return 'orange';
  return 'grey';
}

function progressFillClass(s) {
  s = (s || '').toUpperCase();
  if (s === 'SUCCESS') return 'success';
  if (s === 'FAILED' || s === 'PARTIAL_FAILURE') return 'error';
  if (s === 'RUNNING') return 'running';
  return 'warning';
}

function getProc(ess, type) {
  if (type === 'FINAL') return ess.final;
  return ess.prelim;
}

function getStatus(ess, type) {
  if (type === 'PRELIM') return ess.prelim.status;
  if (type === 'FINAL') return ess.final.status;
  return ess.status;
}

function getEta(ess, type) {
  var proc = getProc(ess, type);
  if (proc.status === 'SUCCESS') return 'Done';
  if (proc.status === 'FAILED' || proc.status === 'PARTIAL_FAILURE') return 'Blocked';
  return proc.eta || '\u2014';
}

function getDatasetStatus(ds, type) {
  return type === 'FINAL' ? ds.final_status : ds.prelim_status;
}

function extractDagId(dagRunId) {
  if (!dagRunId) return '\u2014';
  var parts = dagRunId.split('_');
  // DAG_RUN_ID format: FGW_{dag_id}_{business_date}_{slice}_{unique_int}
  // Extract the dag_id portion
  return parts.slice(1, parts.length - 2).join('_');
}

// ===== UPDATE SUMMARY CARDS =====

function updateSummaryCards(data) {
  var s = data.summary;
  document.getElementById('summary-total').textContent = s.total;
  document.getElementById('summary-completed').textContent = s.completed;
  document.getElementById('summary-running').textContent = s.running;
  document.getElementById('summary-failed').textContent = s.failed;
  document.getElementById('summary-not-started').textContent = s.not_started;
}

// ===== RENDER EXPANDED ROW =====

function renderExpandedRow(ess, type) {
  var ds = ess.datasets;
  if (!ds || !ds.length) return '';

  var rows = ds
    .map(function (d) {
      var st = getDatasetStatus(d, type);
      var cls = statusBadgeClass(st);
      var lbl = statusLabel(st);
      var slices = d.slice_count > 0 ? d.slices_success + '/' + d.slice_count : '\u2014';
      var started = d.created_date
        ? new Date(d.created_date).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
        : '\u2014';
      var dur = st === 'RUNNING' ? formatDuration(d.duration_minutes) + '...' : formatDuration(d.duration_minutes);
      var dotHtml = cls !== 'cancelled' ? '<span class="status-dot ' + cls + '"></span>' : '';

      return (
        '<tr>' +
        '<td><span class="seq-badge">' + d.sequence_order + '</span></td>' +
        '<td>' + d.dataset_id + '</td>' +
        '<td>' + extractDagId(d.latest_dag_run_id) + '</td>' +
        '<td><span class="status-badge small ' + cls + '">' + dotHtml + lbl + '</span></td>' +
        '<td>' + slices + '</td>' +
        '<td>' + started + '</td>' +
        '<td>' + dur + '</td>' +
        '</tr>'
      );
    })
    .join('');

  return (
    '<tr class="expanded-row"><td colspan="9"><div class="expanded-content">' +
    '<table class="dataset-table"><thead><tr>' +
    '<th>Seq</th><th>Dataset ID</th><th>DAG ID</th><th>Status</th><th>Slices</th><th>Started</th><th>Duration</th>' +
    '</tr></thead><tbody>' +
    rows +
    '</tbody></table>' +
    '<div class="quick-actions">' +
    '<button class="quick-action">View Task Details</button>' +
    '<button class="quick-action">RCA for Failed</button>' +
    '<button class="quick-action">AWS Metrics</button>' +
    '<button class="quick-action" onclick="event.stopPropagation(); askSentry(\'' + ess.display_name + '\')">Ask SENTRY AI</button>' +
    '</div>' +
    '</div></td></tr>'
  );
}

// ===== RENDER TABLE =====

function renderEssentialsTable(data, type) {
  var body = document.getElementById('essentialsBody');
  document.getElementById('batchCount').textContent = data.essentials.length + ' batches';
  var html = '';

  data.essentials.forEach(function (ess) {
    var isExpanded = expandedEssential === ess.essential_name;
    var status = getStatus(ess, type);
    var cls = statusBadgeClass(status);
    var lbl = statusLabel(status);
    var proc = getProc(ess, type);
    var pct = proc.total_datasets > 0 ? Math.round((proc.success / proc.total_datasets) * 100) : 0;
    var eta = getEta(ess, type);
    var etaStyle = eta === 'Blocked' ? ' style="color:var(--error)"' : '';
    var dotHtml = cls !== 'cancelled' ? '<span class="status-dot ' + cls + '"></span>' : '';

    html +=
      '<tr data-essential="' + ess.essential_name + '" onclick="toggleRow(\'' + ess.essential_name + '\')"' +
      (isExpanded ? ' style="background:rgba(47,181,160,0.03)"' : '') + '>' +
      '<td><span class="expand-arrow' + (isExpanded ? ' expanded' : '') + '">' + CHEVRON_SVG + '</span></td>' +
      '<td><a class="batch-link" href="#" onclick="event.preventDefault()">' + ess.display_name + '</a></td>' +
      '<td><span class="status-badge ' + cls + '">' + dotHtml + lbl + '</span></td>' +
      '<td><div class="processing-indicators">' +
      '<div class="proc-row"><span class="proc-label">Prelim:</span> <span class="proc-dot ' + procDotClass(ess.prelim.status) + '"></span></div>' +
      '<div class="proc-row"><span class="proc-label">Final:</span> <span class="proc-dot ' + procDotClass(ess.final.status) + '"></span></div>' +
      '</div></td>' +
      '<td><div class="progress-bar-container"><div class="progress-track"><div class="progress-fill ' + progressFillClass(status) + '" style="width:' + pct + '%"></div></div><span class="progress-text">' + proc.progress + '</span></div></td>' +
      '<td class="mono">' + proc.total_datasets + '</td>' +
      '<td class="timestamp">' + formatTime(proc.started_at) + '</td>' +
      '<td class="timestamp">' + formatTime(proc.last_updated) + '</td>' +
      '<td class="timestamp"' + etaStyle + '>' + eta + '</td>' +
      '</tr>';

    if (isExpanded) {
      html += renderExpandedRow(ess, type);
    }
  });

  body.innerHTML = html;
}

// ===== TOGGLE EXPAND =====

function toggleRow(name) {
  expandedEssential = expandedEssential === name ? null : name;
  renderDashboard();
}

// ===== FETCH DATA =====

function fetchEssentials() {
  var params = new URLSearchParams();
  if (currentBusinessDate) params.set('business_date', currentBusinessDate);
  if (currentProcessingType !== 'ALL') params.set('processing_type', currentProcessingType);

  var url = '/api/essentials' + (params.toString() ? '?' + params.toString() : '');

  fetch(url)
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      hideErrorBanner();
      updateSummaryCards(data);
      renderEssentialsTable(data, currentProcessingType);
    })
    .catch(function () {
      // Fallback to mock data, show error banner
      showErrorBanner('Failed to load data \u2014 showing cached data. Retrying in 30s.');
      updateSummaryCards(MOCK_DATA);
      renderEssentialsTable(MOCK_DATA, currentProcessingType);
    });
}

// ===== ERROR BANNER =====

function showErrorBanner(msg) {
  var existing = document.getElementById('errorBanner');
  if (existing) existing.remove();

  var banner = document.createElement('div');
  banner.id = 'errorBanner';
  banner.className = 'error-banner';
  banner.innerHTML = '<span>' + msg + '</span><button onclick="fetchEssentials()">Retry</button>';

  var summaryRow = document.querySelector('.summary-row');
  if (summaryRow) {
    summaryRow.parentNode.insertBefore(banner, summaryRow.nextSibling);
  }
}

function hideErrorBanner() {
  var existing = document.getElementById('errorBanner');
  if (existing) existing.remove();
}

// ===== RENDER DASHBOARD =====

function renderDashboard() {
  // Try live API first, fall back to mock data
  fetchEssentials();
}

// ===== ASK SENTRY AI =====

function askSentry(essentialName) {
  if (typeof sendChatMessage === 'function') {
    sendChatMessage('What is the status of ' + essentialName + '?');
  }
}

// ===== EVENT HANDLERS =====

document.addEventListener('DOMContentLoaded', function () {
  // Initialize date picker
  var datePicker = document.getElementById('datePicker');
  if (datePicker) {
    datePicker.value = currentBusinessDate;
    datePicker.addEventListener('change', function () {
      currentBusinessDate = this.value;
      renderDashboard();
      // Update chat context bar
      var contextDate = document.getElementById('contextDate');
      if (contextDate) {
        contextDate.innerHTML = formatDate(currentBusinessDate) + ' <span class="remove">&times;</span>';
      }
    });
  }

  // View toggle (PRELIM / FINAL / ALL)
  var viewToggle = document.getElementById('viewToggle');
  if (viewToggle) {
    viewToggle.addEventListener('click', function (e) {
      var btn = e.target.closest('.view-toggle-btn');
      if (!btn) return;
      currentProcessingType = btn.dataset.type;
      this.querySelectorAll('.view-toggle-btn').forEach(function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      renderDashboard();
    });
  }

  // Refresh button
  var refreshBtn = document.getElementById('refreshBtn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      renderDashboard();
    });
  }

  // Nav tabs
  var headerNav = document.querySelector('.header-nav');
  if (headerNav) {
    headerNav.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (!a) return;
      e.preventDefault();
      this.querySelectorAll('a').forEach(function (l) {
        l.classList.remove('active');
      });
      a.classList.add('active');
    });
  }

  // Initial render
  renderDashboard();

  // Auto-refresh every 60 seconds
  autoRefreshInterval = setInterval(renderDashboard, AUTO_REFRESH_MS);
});
