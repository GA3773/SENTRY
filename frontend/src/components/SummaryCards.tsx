import './SummaryCards.css';

interface SummaryCardsProps {
  total: number;
  completed: number;
  running: number;
  failed: number;
  notStarted: number;
}

export default function SummaryCards({ total, completed, running, failed, notStarted }: SummaryCardsProps) {
  return (
    <div className="summary-row">
      <div className="summary-card">
        <div className="summary-card-label">Total Batches</div>
        <div className="summary-card-value total">{total}</div>
        <div className="summary-card-sub">Tracking today</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-label">Completed</div>
        <div className="summary-card-value success">{completed}</div>
        <div className="summary-card-sub">All steps success</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-label">Running</div>
        <div className="summary-card-value running">{running}</div>
        <div className="summary-card-sub">In progress</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-label">Failed</div>
        <div className="summary-card-value error">{failed}</div>
        <div className="summary-card-sub">Needs attention</div>
      </div>
      <div className="summary-card">
        <div className="summary-card-label">Not Started</div>
        <div className="summary-card-value warning">{notStarted}</div>
        <div className="summary-card-sub">Pending trigger</div>
      </div>
    </div>
  );
}
