import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Download, RefreshCw, VideoOff } from 'lucide-react';
import * as echarts from 'echarts/core';
import type { EChartsOption } from 'echarts';
import { LineChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { mediaUrl } from './api';

echarts.use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

const states: Record<string, string> = { queued: '排队中', running: '检测中', processing: '检测中', reviewing: '模型复核中', completed: '已完成', failed: '失败' };
export function Badge({ value }: { value?: string }) {
  const tone = ['异常', '疑似异常', 'failed', '复核失败'].includes(value || '') ? 'danger'
    : ['正常', 'completed'].includes(value || '') ? 'success' : 'pending';
  return <span className={`badge ${tone}`}><i />{states[value || ''] || value || '待复核'}</span>;
}
export function Notice({ text, retry }: { text: string; retry?: () => void }) {
  return <div className="notice" role="alert"><AlertCircle size={18}/><span>{text}</span>{retry && <button onClick={retry}>重试</button>}</div>;
}
export function Empty({ text = '暂无记录' }: { text?: string }) { return <div className="empty">{text}</div>; }
export function Pager({ page, total, size = 10, onChange }: { page: number; total: number; size?: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return <div className="pager"><span>共 {total} 条记录</span><div><button disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><span>{page} / {pages}</span><button disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</button></div></div>;
}
export function Player({ path, version, title }: { path?: string; version?: string | number; title: string }) {
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [waiting, setWaiting] = useState(true);
  const url = mediaUrl(path, attempt || version);
  useEffect(() => { setError(false); setWaiting(true); setAttempt(0); }, [path, version]);
  return <div className="player">
    <div className="section-heading"><h3>{title}</h3>{url && <a href={url} download title="下载视频" aria-label="下载视频"><Download size={17}/></a>}</div>
    {!url ? <div className="video-empty"><VideoOff size={28}/><span>完整视频尚未就绪</span></div> : <>
      <video key={url} src={url} controls playsInline preload="metadata" aria-label={title}
        onLoadedMetadata={() => setWaiting(false)} onError={() => { setError(true); setWaiting(false); }} />
      {waiting && !error && <p className="muted" role="status">正在加载视频…</p>}
      {error && <Notice text="视频加载失败，文件可能已被清理或连接中断" retry={() => { setError(false); setWaiting(true); setAttempt(Date.now()); }}/ >}
      <div className="video-actions"><a href={url} target="_blank" rel="noreferrer">单独打开视频</a><button className="icon-button" title="重新加载视频" aria-label="重新加载视频" onClick={() => { setError(false); setWaiting(true); setAttempt(Date.now()); }}><RefreshCw size={15}/></button></div>
    </>}
  </div>;
}
export function Chart({ option, label }: { option: EChartsOption; label: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = echarts.init(host.current);
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [option]);
  return <div className="chart" role="img" aria-label={label} ref={host}/>;
}
