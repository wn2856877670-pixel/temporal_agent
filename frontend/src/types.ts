export interface QwenResult { conclusion?: string; confidence?: number | null; evidence?: string; raw?: string }
export interface TaskEvent {
  event_id: string; video_url?: string; timestamp_seconds?: number; reason?: string; qwen_result?: QwenResult;
}
export interface Task {
  job_id: string; original_name: string; state: string; progress: number;
  created_at?: string; created_at_ts?: number; finished_at_ts?: number;
  event_count?: number; frame?: number; total_frames?: number; eta_seconds?: number | null;
  queue_position?: number | null; processed_video_url?: string; output_url?: string;
  error?: string; result?: QwenResult; events: TaskEvent[];
}
export interface HistoryTask {
  task_id: string; filename: string; status: string; created_at: string;
  finished_at?: string; event_count: number; error_message?: string;
}
export interface BehaviorEvent {
  id: number; task_id: string; event_index: number; event_type?: string;
  start_time?: number; end_time?: number; duration?: number;
  confidence?: number | null; qwen_result?: string; qwen_confidence?: number | null;
  clip_url?: string; created_at: string;
}
export interface Statistics {
  total_tasks: number; total_events: number; total_abnormal: number;
  today_tasks: number; today_events: number; today_abnormal: number;
}
export interface DailyPoint { date: string; count: number }
export interface TypePoint { event_type: string; count: number }
export interface EventPage { events: BehaviorEvent[]; total: number; page: number; page_size: number }
export interface EventFilters {
  task_id?: string; start_date?: string; end_date?: string; event_type?: string; qwen_result?: string;
}
