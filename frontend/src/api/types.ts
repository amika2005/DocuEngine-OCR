export interface Me {
  id: string;
  email: string;
  display_name: string;
  role: 'super_admin' | 'company_admin' | 'user';
  company_id: string | null;
}

export interface Document {
  id: string;
  original_filename: string;
  doc_type: string;
  status: string;
  page_count: number;
  byte_size: number;
  batch_id: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DocumentList {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

export interface Page {
  id: string;
  page_number: number;
  status: string;
  width_px: number;
  height_px: number;
}

export interface OcrResult {
  id: string;
  markdown: string;
  layout_json: { regions?: Region[] };
  avg_confidence: number | null;
  engine: string;
}

export interface Region {
  bbox: number[];
  kind: string;
  markdown: string;
  confidence: number;
  vertical: boolean;
}

export interface Correction {
  id: string;
  page_id: string;
  ocr_result_id: string;
  original_markdown: string;
  corrected_markdown: string;
  region_index: number | null;
  status: string;
  created_at: string;
}

export interface Company {
  id: string;
  name: string;
  name_kana: string | null;
  slug: string;
  status: string;
  max_users: number;
  max_devices: number;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  last_login_at: string | null;
}

export interface Device {
  id: string;
  name: string;
  status: string;
  last_seen_at: string | null;
  created_at: string;
  token?: string;
}

export interface TrainingRun {
  id: string;
  status: string;
  dataset_stats: Record<string, unknown>;
  eval_report: Record<string, unknown>;
  triggered_by: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ModelVersion {
  id: string;
  name: string;
  kind: string;
  status: string;
  metrics: Record<string, unknown>;
  activated_at: string | null;
  created_at: string;
}
