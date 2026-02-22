import './Header.css';

const navItems = ['Dashboard', 'Batch Explorer', 'RCA Analysis', 'AWS Metrics', 'Predictions', 'Audit Log'];

export default function Header() {
  return (
    <header className="header">
      <div className="header-brand">
        <h1>SENTRY</h1>
        <span className="version">Version: 1.0.0-alpha</span>
      </div>

      <nav className="header-nav">
        {navItems.map((item) => (
          <a
            key={item}
            href="#"
            className={item === 'Dashboard' ? 'active' : ''}
            onClick={(e) => e.preventDefault()}
          >
            {item}
          </a>
        ))}
      </nav>

      <div className="header-right">
        <span className="env-badge">PROD</span>
        <div className="connection-dot" title="Connected to RDS & Airflow" />
        <div className="header-icon" title="Settings">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
          </svg>
        </div>
        <div className="header-icon" title="Notifications">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
          </svg>
        </div>
        <div className="header-icon" title="Help">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01" />
          </svg>
        </div>
      </div>
    </header>
  );
}
