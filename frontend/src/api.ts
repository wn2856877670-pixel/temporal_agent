import axios from 'axios';
import type { Task, HistoryTask, Statistics, DailyPoint, TypePoint, EventFilters, EventPage, BehaviorEvent } from './types';

export const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '', timeout: 20000 });
http.interceptors.response.use(response => response, error => {
  if (axios.isCancel(error)) return Promise.reject(error);
  const detail = error.response?.data?.detail;
  const message = typeof detail === 'string' ? detail : error.response?.status === 404
    ? '记录不存在或已被清理' : error.code === 'ECONNABORTED' ? '请求超时，请稍后重试'
      : '服务连接失败，请检查云端服务和端口转发';
  return Promise.reject(new Error(message));
});
export const api = {
  jobs: async (signal?: AbortSignal) => (await http.get<{ jobs: Task[] }>('/api/jobs', { signal })).data.jobs,
  job: async (id: string, signal?: AbortSignal) => (await http.get<Task>(`/api/jobs/${encodeURIComponent(id)}`, { signal })).data,
  history: async (signal?: AbortSignal) => (await http.get<{ tasks: HistoryTask[] }>('/api/history/tasks', { params: { limit: 1000 }, signal })).data.tasks,
  overview: async (signal?: AbortSignal) => (await http.get<Statistics>('/api/statistics/overview', { signal })).data,
  daily: async (signal?: AbortSignal) => (await http.get<DailyPoint[]>('/api/statistics/daily', { params: { days: 7 }, signal })).data,
  types: async (signal?: AbortSignal) => (await http.get<TypePoint[]>('/api/statistics/event-types', { signal })).data,
  events: async (filters: EventFilters, page: number, signal?: AbortSignal) =>
    (await http.get<EventPage>('/api/history/events', { params: { ...filters, page, page_size: 10 }, signal })).data,
  event: async (id: string, signal?: AbortSignal) => (await http.get<BehaviorEvent>(`/api/history/events/${encodeURIComponent(id)}`, { signal })).data,
  upload: async (file: File, progress: (percent: number) => void) => {
    const form = new FormData(); form.append('video', file);
    return (await http.post<{ job: Task }>('/api/jobs', form, {
      timeout: 3600000,
      onUploadProgress: event => progress(event.total ? Math.min(100, Math.round(event.loaded * 100 / event.total)) : 0),
    })).data.job;
  },
};

export function mediaUrl(path?: string, version?: string | number) {
  if (!path) return '';
  const url = new URL(path, http.defaults.baseURL || window.location.origin);
  if (!['http:', 'https:'].includes(url.protocol)) return '';
  if (version !== undefined) url.searchParams.set('v', String(version));
  return url.href;
}
export const triggerLabels: Record<string, string> = {
  any_pair_iou: '任意两鹿重叠', overlap_iou: '目标公鹿重叠', male_overlap: '目标公鹿重叠', near_distance: '目标公鹿靠近', male_near: '目标公鹿靠近',
};
export const triggerLabel = (key?: string) => key ? triggerLabels[key] || key : '未分类';
export const confidence = (value?: number | null) => value == null ? '未提供' : `${(value * 100).toFixed(0)}%`;
export const seconds = (value?: number | null) => value == null ? '—' : `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
