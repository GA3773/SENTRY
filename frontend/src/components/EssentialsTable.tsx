import { useState } from 'react';
import { Essential } from '../types';
import StatusBadge from './StatusBadge';
import ExpandedRow from './ExpandedRow';
import './EssentialsTable.css';

interface EssentialsTableProps {
  essentials: Essential[];
  processingType: string;
}

function formatTime(isoDate: string | null): string {
  if (!isoDate) return '\u2014';
  const d = new Date(isoDate);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function getOverallStatus(essential: Essential, processingType: string): string {
  if (processingType === 'PRELIM') return essential.prelim.status;
  if (processingType === 'FINAL') return essential.final.status;
  return essential.status;
}

function getProcDotClass(status: string): string {
  switch (status.toUpperCase()) {
    case 'SUCCESS': return 'green';
    case 'FAILED':
    case 'PARTIAL_FAILURE': return 'red';
    case 'RUNNING': return 'blue';
    case 'NOT_STARTED': return 'grey';
    case 'WAITING': return 'orange';
    default: return 'grey';
  }
}

function getProgressFillClass(status: string): string {
  switch (status.toUpperCase()) {
    case 'SUCCESS': return 'success';
    case 'FAILED':
    case 'PARTIAL_FAILURE': return 'error';
    case 'RUNNING': return 'running';
    case 'WAITING': return 'warning';
    default: return 'success';
  }
}

function getProgress(essential: Essential, processingType: string) {
  const proc = processingType === 'FINAL' ? essential.final : essential.prelim;
  const total = proc.total_datasets;
  const done = proc.success;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return { progress: proc.progress, pct };
}

function getEta(essential: Essential, processingType: string): string {
  const proc = processingType === 'FINAL' ? essential.final : essential.prelim;
  if (proc.status === 'SUCCESS') return 'Done';
  if (proc.status === 'FAILED' || proc.status === 'PARTIAL_FAILURE') return 'Blocked';
  return proc.eta || '\u2014';
}

export default function EssentialsTable({ essentials, processingType }: EssentialsTableProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>('TB-Derivatives');

  const toggleRow = (name: string) => {
    setExpandedRow(expandedRow === name ? null : name);
  };

  return (
    <div className="section-card">
      <div className="section-header">
        <div className="section-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
          All Essentials
        </div>
        <span className="section-badge">{essentials.length} batches</span>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ width: 32 }}></th>
            <th>
              Essential
              <span className="filter-icon">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
                </svg>
              </span>
            </th>
            <th>Status</th>
            <th>Prelim / Final</th>
            <th>Progress</th>
            <th>Datasets</th>
            <th>Started</th>
            <th>Last Updated</th>
            <th>ETA</th>
          </tr>
        </thead>
        {essentials.map((ess) => {
            const isExpanded = expandedRow === ess.essential_name;
            const status = getOverallStatus(ess, processingType);
            const { progress, pct } = getProgress(ess, processingType);
            const fillClass = getProgressFillClass(status);
            const eta = getEta(ess, processingType);
            const proc = processingType === 'FINAL' ? ess.final : ess.prelim;

            return (
              <tbody key={ess.essential_name}>
                <tr
                  className={isExpanded ? 'row-expanded' : ''}
                  onClick={() => toggleRow(ess.essential_name)}
                >
                  <td>
                    <span className={`expand-arrow${isExpanded ? ' expanded' : ''}`}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                    </span>
                  </td>
                  <td>
                    <a className="batch-link" href="#" onClick={(e) => e.preventDefault()}>
                      {ess.display_name}
                    </a>
                  </td>
                  <td>
                    <StatusBadge status={status} />
                  </td>
                  <td>
                    <div className="processing-indicators">
                      <div className="proc-row">
                        <span className="proc-label">Prelim:</span>
                        <span className={`proc-dot ${getProcDotClass(ess.prelim.status)}`} />
                      </div>
                      <div className="proc-row">
                        <span className="proc-label">Final:</span>
                        <span className={`proc-dot ${getProcDotClass(ess.final.status)}`} />
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="progress-bar-container">
                      <div className="progress-track">
                        <div
                          className={`progress-fill ${fillClass}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="progress-text">{progress}</span>
                    </div>
                  </td>
                  <td className="mono">{proc.total_datasets}</td>
                  <td className="timestamp">{formatTime(proc.started_at)}</td>
                  <td className="timestamp">{formatTime(proc.last_updated)}</td>
                  <td className={`timestamp${eta === 'Blocked' ? ' eta-blocked' : ''}`}>
                    {eta}
                  </td>
                </tr>
                {isExpanded && ess.datasets.length > 0 && (
                  <tr className="expanded-row">
                    <td colSpan={9}>
                      <ExpandedRow datasets={ess.datasets} processingType={processingType} />
                    </td>
                  </tr>
                )}
              </tbody>
            );
          })}
      </table>
    </div>
  );
}
