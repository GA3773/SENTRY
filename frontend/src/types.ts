export interface EssentialDataset {
  dataset_id: string;
  sequence_order: number;
  prelim_status: string;
  final_status: string;
  slice_count: number;
  slices_success: number;
  slices_failed: number;
  latest_dag_run_id: string;
  duration_minutes: number;
  created_date: string | null;
  updated_date: string | null;
}

export interface ProcessingStatus {
  status: string;
  total_datasets: number;
  success: number;
  failed: number;
  running: number;
  not_started: number;
  progress: string;
  started_at: string | null;
  last_updated: string | null;
  eta: string | null;
}

export interface Essential {
  essential_name: string;
  display_name: string;
  status: string;
  prelim: ProcessingStatus;
  final: ProcessingStatus;
  datasets: EssentialDataset[];
}

export interface EssentialsResponse {
  business_date: string;
  timestamp: string;
  summary: {
    total: number;
    completed: number;
    running: number;
    failed: number;
    not_started: number;
  };
  essentials: Essential[];
}
