import { useState } from 'react';
import Header from './components/Header';
import SummaryCards from './components/SummaryCards';
import PageControls from './components/PageControls';
import EssentialsTable from './components/EssentialsTable';
import ChatPanel from './components/ChatPanel';
import { mockEssentials } from './data/mockEssentials';
import './App.css';

function App() {
  const [processingType, setProcessingType] = useState('PRELIM');
  const data = mockEssentials;

  return (
    <>
      <Header />
      <div className="main-container">
        <div className="dashboard-panel">
          <div className="page-header">
            <div>
              <div className="page-title">Essentials Dashboard</div>
              <div className="page-subtitle">
                Real-time batch processing status across all asset classes
              </div>
            </div>
            <PageControls
              processingType={processingType}
              onProcessingTypeChange={setProcessingType}
              businessDate={data.business_date}
            />
          </div>

          <SummaryCards
            total={data.summary.total}
            completed={data.summary.completed}
            running={data.summary.running}
            failed={data.summary.failed}
            notStarted={data.summary.not_started}
          />

          <EssentialsTable
            essentials={data.essentials}
            processingType={processingType}
          />
        </div>

        <div className="resize-handle" />

        <ChatPanel />
      </div>
    </>
  );
}

export default App;
