import { EssentialDataset } from '../types';
import StatusBadge from './StatusBadge';
import './ExpandedRow.css';

interface ExpandedRowProps {
  datasets: EssentialDataset[];
  processingType: string;
}

function formatDuration(minutes: number): string {
  if (minutes <= 0) return '\u2014';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatStartTime(isoDate: string | null): string {
  if (!isoDate) return '\u2014';
  const d = new Date(isoDate);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function getDatasetStatus(dataset: EssentialDataset, processingType: string): string {
  if (processingType === 'FINAL') return dataset.final_status;
  return dataset.prelim_status;
}

export default function ExpandedRow({ datasets, processingType }: ExpandedRowProps) {
  return (
    <div className="expanded-content">
      <table className="dataset-table">
        <thead>
          <tr>
            <th>Seq</th>
            <th>Dataset ID</th>
            <th>DAG ID</th>
            <th>Status</th>
            <th>Slices</th>
            <th>Started</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((ds) => {
            const status = getDatasetStatus(ds, processingType);
            const dagId = ds.latest_dag_run_id
              ? ds.latest_dag_run_id.split('_').slice(1, -2).join('_')
              : '\u2014';
            const sliceText = ds.slice_count > 0
              ? `${ds.slices_success}/${ds.slice_count}`
              : '\u2014';
            const durationText = status === 'RUNNING'
              ? `${formatDuration(ds.duration_minutes)}...`
              : formatDuration(ds.duration_minutes);

            return (
              <tr key={ds.dataset_id}>
                <td>
                  <span className="seq-badge">{ds.sequence_order}</span>
                </td>
                <td>{ds.dataset_id}</td>
                <td>{dagId}</td>
                <td>
                  <StatusBadge status={status} small />
                </td>
                <td>{sliceText}</td>
                <td>{formatStartTime(ds.created_date)}</td>
                <td>{durationText}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="quick-actions">
        <button className="quick-action">View Task Details</button>
        <button className="quick-action">RCA for Failed</button>
        <button className="quick-action">AWS Metrics</button>
        <button className="quick-action">Ask SENTRY AI</button>
      </div>
    </div>
  );
}
