import './StatusBadge.css';

interface StatusBadgeProps {
  status: string;
  small?: boolean;
}

function getStatusClass(status: string): string {
  switch (status.toUpperCase()) {
    case 'SUCCESS': return 'success';
    case 'FAILED':
    case 'PARTIAL_FAILURE': return 'failed';
    case 'RUNNING': return 'running';
    case 'WARNING':
    case 'WAITING':
    case 'NOT_STARTED': return 'warning';
    case 'CANCELLED': return 'cancelled';
    default: return 'cancelled';
  }
}

function getDisplayLabel(status: string): string {
  switch (status.toUpperCase()) {
    case 'SUCCESS': return 'SUCCESS';
    case 'FAILED': return 'FAILED';
    case 'PARTIAL_FAILURE': return 'FAILED';
    case 'RUNNING': return 'RUNNING';
    case 'WAITING': return 'WAITING';
    case 'NOT_STARTED': return 'PENDING';
    case 'CANCELLED': return 'CANCELLED';
    default: return status;
  }
}

export default function StatusBadge({ status, small }: StatusBadgeProps) {
  const cls = getStatusClass(status);
  const label = getDisplayLabel(status);

  return (
    <span className={`status-badge ${cls}${small ? ' small' : ''}`}>
      {cls !== 'cancelled' && <span className={`status-dot ${cls}`} />}
      {label}
    </span>
  );
}
