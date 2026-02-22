/* ==========================================================================
   SENTRY — Shared Utilities
   ========================================================================== */

/**
 * Generate a UUID v4 string.
 */
function generateUUID() {
  if (crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0;
    var v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Format an ISO date string to "HH:MM:SS".
 * Returns "—" for null/empty input.
 */
function formatTime(isoString) {
  if (!isoString) return '\u2014';
  var d = new Date(isoString);
  return d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Format a duration in minutes to "Xh Ym" or "Ym".
 * Returns "—" for 0/null/undefined.
 */
function formatDuration(minutes) {
  if (!minutes) return '\u2014';
  var h = Math.floor(minutes / 60);
  var m = minutes % 60;
  return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
}

/**
 * Format a date string to "DD-MMM-YYYY" display format.
 * Returns "—" for null/empty input.
 */
function formatDate(dateString) {
  if (!dateString) return '\u2014';
  var d = new Date(dateString);
  var months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  var day = String(d.getDate()).padStart(2, '0');
  var mon = months[d.getMonth()];
  var year = d.getFullYear();
  return day + '-' + mon + '-' + year;
}

/**
 * DOM helper — create an element with optional class and innerHTML.
 */
function createElement(tag, className, innerHTML) {
  var el = document.createElement(tag);
  if (className) el.className = className;
  if (innerHTML) el.innerHTML = innerHTML;
  return el;
}

/**
 * Get today's date as YYYY-MM-DD string.
 */
function todayISO() {
  var d = new Date();
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}
