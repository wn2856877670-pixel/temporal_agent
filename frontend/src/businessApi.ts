import type { AxiosInstance } from 'axios';
import type { BusinessTask, BusinessProgress, BusinessEvent, Task, BehaviorEvent, EventFilters, QwenResult } from './types';

const state = (value: string) => value === 'RUNNING' ? 'processing' : value.toLowerCase();
const terminal = (value: string) => value === 'COMPLETED' || value === 'FAILED';
function event(e: BusinessEvent): BehaviorEvent {
  return { id: e.id, task_id: e.taskId, event_index: e.eventIndex, event_type: e.eventType,
    start_time: e.startTime, end_time: e.endTime, duration: e.duration, confidence: e.confidence,
    qwen_result: e.qwenResult, qwen_confidence: e.qwenConfidence, clip_url: e.clipUrl, created_at: e.createdAt, evidence: e.evidence };
}
function task(t: BusinessTask, progress?: BusinessProgress, events: BusinessEvent[] = []): Task {
  let result: QwenResult | undefined;
  try { result = t.resultJson ? JSON.parse(t.resultJson) : undefined; } catch { /* Older records can lack a summary. */ }
  return { job_id: t.taskId, original_name: t.fileName, state: state(t.status), created_at: t.createdAt,
    finished_at_ts: t.finishedAt ? new Date(t.finishedAt).getTime() : undefined,
    progress: t.status === 'COMPLETED' ? 100 : Number(progress?.progress || 0), stage: progress?.stage,
    frame: Number(progress?.processedFrames || 0), total_frames: Number(progress?.totalFrames || 0),
    event_count: t.eventCount, error: t.errorMessage, processed_video_url: t.outputUrl, result,
    events: events.map(e => ({ event_id: e.eventId, video_url: e.clipUrl, timestamp_seconds: e.startTime,
      reason: e.eventType, qwen_result: { conclusion: e.qwenResult, confidence: e.qwenConfidence, evidence: e.evidence } })) };
}
export function businessApi(http: AxiosInstance) {
  const list = async (signal?: AbortSignal) => (await http.get<{tasks: BusinessTask[]}>('/api/tasks', {params: {pageSize:1000},signal})).data.tasks;
  return {
    jobs: async (signal?: AbortSignal) => Promise.all((await list(signal)).map(async t => task(t, terminal(t.status) ? undefined : (await http.get<BusinessProgress>(`/api/tasks/${t.taskId}/progress`,{signal})).data))),
    history: async (signal?: AbortSignal) => (await list(signal)).map(t => ({task_id:t.taskId,filename:t.fileName,status:state(t.status),created_at:t.createdAt,event_count:t.eventCount,error_message:t.errorMessage})),
    job: async (id: string, signal?: AbortSignal) => {
      const t = (await http.get<BusinessTask>(`/api/tasks/${encodeURIComponent(id)}`,{signal})).data;
      const [p, e] = await Promise.all([
        terminal(t.status) ? Promise.resolve(undefined) : http.get<BusinessProgress>(`/api/tasks/${encodeURIComponent(id)}/progress`,{signal}).then(r=>r.data),
        http.get<BusinessEvent[]>(`/api/tasks/${encodeURIComponent(id)}/events`,{signal}).then(r=>r.data),
      ]);
      return task(t,p,e);
    },
    upload: async (file: File, progress: (value: number) => void) => {
      const form = new FormData(); form.append('video',file);
      return task((await http.post<BusinessTask>('/api/tasks',form,{timeout:3600000,onUploadProgress:e=>progress(e.total?Math.round(e.loaded*100/e.total):0)})).data);
    },
    events: async (filters: EventFilters,page: number,signal?: AbortSignal) => {
      const {data} = await http.get<{events:BusinessEvent[];total:number;page:number;pageSize:number}>('/api/events',{signal,params:{
        page,pageSize:10,taskId:filters.task_id,startDate:filters.start_date,endDate:filters.end_date,eventType:filters.event_type,qwenResult:filters.qwen_result,
      }});
      return {events:data.events.map(event),total:data.total,page:data.page,page_size:data.pageSize};
    },
    event: async (id:string,signal?:AbortSignal) => event((await http.get<BusinessEvent>(`/api/events/${encodeURIComponent(id)}`,{signal})).data),
  };
}
