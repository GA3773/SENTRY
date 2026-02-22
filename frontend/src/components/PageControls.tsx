import './PageControls.css';

interface PageControlsProps {
  processingType: string;
  onProcessingTypeChange: (type: string) => void;
  businessDate: string;
}

export default function PageControls({ processingType, onProcessingTypeChange, businessDate }: PageControlsProps) {
  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  return (
    <div className="page-controls">
      <div className="view-toggle">
        {['PRELIM', 'FINAL', 'ALL'].map((type) => (
          <button
            key={type}
            className={`view-toggle-btn${processingType === type ? ' active' : ''}`}
            onClick={() => onProcessingTypeChange(type)}
          >
            {type}
          </button>
        ))}
      </div>
      <div className="date-picker">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
        {formatDate(businessDate)}
      </div>
      <button className="refresh-btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="23 4 23 10 17 10" />
          <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
        </svg>
        REFRESH
      </button>
    </div>
  );
}
