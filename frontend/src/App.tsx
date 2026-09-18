import { useCallback, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Navigate, Route, Routes, useParams, useSearchParams } from 'react-router-dom';
import { Activity, ArrowRight, BarChart3, CalendarDays, ChevronRight, ClipboardList, Film, LayoutDashboard, Menu, RefreshCw, ScanLine, Upload, X } from 'lucide-react';
import type { EChartsOption } from 'echarts';
import { api, confidence, seconds, triggerLabel } from './api';
import type { EventFilters, Task } from './types';
import { useResource } from './hooks';
import { Badge, Chart, Empty, Notice, Pager, Player } from './components';

const navigation = [
  { to: '/dashboard', text: '数据看板', icon: LayoutDashboard },
  { to: '/analyze', text: '视频分析', icon: ScanLine },
  { to: '/tasks', text: '任务记录', icon: ClipboardList },
  { to: '/events', text: '行为事件', icon: Film },
];

export default function App() {
  const [open, setOpen] = useState(false);
  // Keep upload state above routes so navigating during upload does not lose it.
  const [upload, setUpload] = useState({ busy: false, percent: 0, error: '', id: '' });
  const submit = async (file: File) => {
    setUpload({ busy: true, percent: 0, error: '', id: '' });
    try {
      const job = await api.upload(file, percent => setUpload(v => ({ ...v, percent })));
      setUpload({ busy: false, percent: 100, error: '', id: job.job_id });
    } catch (error) { setUpload(v => ({ ...v, busy: false, error: (error as Error).message })); }
  };
  return <div className="app">
    {open && <button className="overlay" aria-label="关闭导航" onClick={() => setOpen(false)}/>}
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <Link className="brand" to="/dashboard"><span className="brand-mark"><ScanLine size={25}/></span><span>鹿场智巡<small>梅花鹿行为分析平台</small></span></Link>
      <div className="nav-caption">工作空间</div>
      <nav>{navigation.map(({ to, text, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setOpen(false)}><Icon size={19}/>{text}<ChevronRight size={15}/></NavLink>)}</nav>
      <div className="sidebar-foot"><Activity size={17}/><span>智能养殖 · 视频分析</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div><button className="icon-button menu" aria-label="打开导航" onClick={() => setOpen(!open)}>{open ? <X/> : <Menu/>}</button><span>养殖监测中心</span><ChevronRight size={15}/><span className="muted">行为分析</span></div><span className="top-tag">DEER MONITOR</span></header>
      <main>
        {upload.busy && <div className="upload-banner" role="status">视频上传中 · {upload.percent}%{upload.percent === 100 ? ' · 正在创建任务' : ''}</div>}
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace/>}/>
          <Route path="/dashboard" element={<Dashboard/>}/>
          <Route path="/analyze" element={<Analyze upload={upload} submit={submit}/>}/>
          <Route path="/tasks" element={<Tasks/>}/>
          <Route path="/events" element={<Events/>}/>
          <Route path="/events/:eventId" element={<EventDetail/>}/>
          <Route path="/detect" element={<LegacyDetect/>}/>
          <Route path="/analysis" element={<Navigate to="/dashboard" replace/>}/>
          <Route path="*" element={<><PageTitle title="页面不存在"/><Link to="/dashboard">返回数据看板</Link></>}/>
        </Routes>
      </main>
    </div>
  </div>;
}
function LegacyDetect() { const [p] = useSearchParams(); return <Navigate replace to={`/analyze${p.get('job') ? '?task=' + encodeURIComponent(p.get('job')!) : ''}`}/>; }
function PageTitle({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return <div className="page-title"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{children}</div>;
}
function Dashboard() {
  const load = useCallback(async (s: AbortSignal) => {
    const [stats, daily, types, tasks] = await Promise.all([api.overview(s), api.daily(s), api.types(s), api.history(s)]);
    return { stats, daily, types, tasks };
  }, []);
  const { data, error, loading, refresh } = useResource(load, 30000);
  const trend = useMemo<EChartsOption>(() => ({ color: ['#1769cf'], tooltip: { trigger: 'axis' }, grid: { left: 42, right: 22, top: 24, bottom: 34 }, xAxis: { type: 'category', data: data?.daily.map(d => d.date.slice(5)), axisLine: { lineStyle: { color: '#d9e1e9' } }, axisLabel: { color: '#65758a' } }, yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#eef1f5' } } }, series: [{ type: 'line', data: data?.daily.map(d => d.count), smooth: true, symbolSize: 7, areaStyle: { color: '#e9f2ff' } }] }), [data?.daily]);
  const types = useMemo<EChartsOption>(() => ({ color: ['#1769cf', '#26a18d', '#e7aa3d', '#7b91ad'], tooltip: { trigger: 'item' }, legend: { bottom: 0, type: 'scroll' }, series: [{ type: 'pie', radius: ['46%', '70%'], center: ['50%', '43%'], label: { show: false }, data: data?.types.map(d => ({ name: triggerLabel(d.event_type), value: d.count })) }] }), [data?.types]);
  return <><PageTitle title="数据看板" subtitle="鹿群行为监测概览"><button className="secondary" onClick={refresh}><RefreshCw size={16}/>刷新</button></PageTitle>
    {error && <Notice text={error} retry={refresh}/>}
    <div className="metrics">{[
      ['累计检测任务', data?.stats.total_tasks, ClipboardList], ['累计候选事件', data?.stats.total_events, Film],
      ['今日检测任务', data?.stats.today_tasks, CalendarDays], ['今日候选事件', data?.stats.today_events, Activity],
    ].map(([label, value, Icon], i) => { const Glyph = Icon as typeof Activity; return <div className={`metric metric-${i}`} key={String(label)}><div><span>{String(label)}</span><Glyph size={19}/></div><strong>{value == null ? '—' : Number(value).toLocaleString()}</strong><small>{loading && !data ? '正在加载' : i < 2 ? '历史累计' : '今日新增'}</small></div>; })}</div>
    <div className="confirmation"><span><i/>Qwen 判为异常（含疑似）</span><b>累计 {data?.stats.total_abnormal ?? '—'} <small>个</small></b><b>今日 {data?.stats.today_abnormal ?? '—'} <small>个</small></b></div>
    <div className="chart-grid"><section><div className="section-heading"><h2>最近 7 天事件趋势</h2><span className="muted">候选事件</span></div>{data ? <Chart option={trend} label="最近七天候选事件趋势折线图"/> : <Empty text={error ? '统计暂不可用' : '正在加载统计…'}/>}</section><section><div className="section-heading"><h2>候选触发类型</h2><BarChart3 size={18}/></div>{data?.types.length ? <Chart option={types} label="候选事件触发类型统计图"/> : <Empty text={loading ? '正在加载统计…' : '暂无候选事件'}/>}<p className="muted chart-note">行为分类尚未提供</p></section></div>
    <section><div className="section-heading"><h2>最近检测任务</h2><Link to="/tasks">全部任务 <ArrowRight size={15}/></Link></div><div className="table-wrap"><table><thead><tr><th>视频名称</th><th>创建时间</th><th>状态</th><th>候选事件</th><th>操作</th></tr></thead><tbody>{data?.tasks.slice(0, 5).map(t => <tr key={t.task_id}><td>{t.filename}</td><td>{t.created_at}</td><td><Badge value={t.status}/></td><td>{t.event_count}</td><td><Link to={`/analyze?task=${encodeURIComponent(t.task_id)}`}>查看任务</Link></td></tr>)}</tbody></table></div>{!data?.tasks.length && <Empty text={loading ? '正在加载…' : '暂无检测任务'}/>}</section>
  </>;
}
function Analyze({ upload, submit }: { upload: { busy: boolean; percent: number; error: string; id: string }; submit: (file: File) => Promise<void> }) {
  const [params, setParams] = useSearchParams();
  const [file, setFile] = useState<File>(); const [validation, setValidation] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const resource = useResource(api.jobs, 3000);
  const selected = params.get('task') || upload.id || resource.data?.[0]?.job_id;
  const choose = (value?: File) => {
    setValidation('');
    if (value && (!/\.(mp4|avi|mov|mkv)$/i.test(value.name) || !value.size || value.size > 4096 * 1024 * 1024)) {
      setValidation('请选择不超过 4 GB 的 MP4、AVI、MOV 或 MKV 视频'); setFile(undefined); return;
    }
    setFile(value);
  };
  return <><PageTitle title="视频分析" subtitle="检测任务与 Qwen-VL 复核"/>
    <section><div className="section-heading"><h2>上传待检测视频</h2><span className="muted">单个视频 · 最大 4 GB</span></div>
      <div className="upload-row"><label className="file-picker" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!upload.busy) choose(e.dataTransfer.files[0]); }}><Upload size={23}/><span><b>{file?.name || '选择或拖入视频'}</b><small>{file ? `${(file.size / 1048576).toFixed(1)} MB` : 'MP4 / AVI / MOV / MKV'}</small></span><input aria-label="选择视频" ref={input} type="file" accept=".mp4,.avi,.mov,.mkv" disabled={upload.busy} onChange={e => choose(e.target.files?.[0])}/></label><button className="primary" disabled={!file || upload.busy} onClick={async () => { if (file) { setParams({}); await submit(file); } }}><ScanLine size={17}/>{upload.busy ? '上传中…' : '开始分析'}</button></div>
      {upload.busy && <progress value={upload.percent} max={100} aria-label="上传进度"/>}
      {(validation || upload.error) && <Notice text={validation || upload.error}/>}
      {upload.id && !upload.busy && <p className="success-text" role="status">任务已提交 <Link to={`/analyze?task=${encodeURIComponent(upload.id)}`}>查看进度</Link></p>}
    </section>
    {resource.error && <Notice text={resource.error} retry={resource.refresh}/>}
    <div className="analysis-grid"><section className="task-main"><div className="section-heading"><h2>当前任务与检测结果</h2></div>{selected ? <TaskDetail key={selected} id={selected}/> : <Empty text={resource.loading ? '正在加载任务…' : '上传视频后开始分析'}/>}</section>
      <section className="recent"><div className="section-heading"><h2>最近任务</h2><span className="muted">{resource.data?.length ?? 0}</span></div><div className="task-list">{resource.data?.map(t => <button key={t.job_id} className={selected === t.job_id ? 'selected' : ''} onClick={() => setParams({ task: t.job_id })}><div><b>{t.original_name}</b><small>{t.created_at}</small></div><div className="task-state"><Badge value={t.state}/><span>{t.progress}%</span></div></button>)}</div>{!resource.data?.length && <Empty/>}</section></div>
  </>;
}
function TaskDetail({ id }: { id: string }) {
  const [clipsOpen, setClipsOpen] = useState(false);
  const load = useCallback((s: AbortSignal) => api.job(id, s), [id]);
  const { data: job, error, refresh } = useResource(load, 3000);
  if (!job) return error ? <Notice text={`${error}。历史事件仍可在行为事件页查询。`} retry={refresh}/> : <Empty text="正在读取任务…"/>;
  const completed = job.state === 'completed';
  const events = job.events || [];
  const noCandidates = completed && (job.event_count ?? events.length) === 0;
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  const path = completed ? job.processed_video_url || job.output_url : undefined;
  return <>
    {error && <Notice text={error} retry={refresh}/>}
    <div className="task-heading"><div><h3>{job.original_name}</h3><small className="muted">{job.created_at}</small></div><Badge value={job.state}/></div>
    <div className="progress-label"><span>{job.state === 'queued' ? `等待检测${job.queue_position ? ` · 队列位置 ${job.queue_position}` : ''}` : completed ? `检测完成 · ${job.event_count ?? events.length} 个候选事件` : job.state === 'failed' ? '任务失败' : progress >= 95 ? '检测后处理 / 模型复核中' : '正在检测视频'}</span><b>{progress}%</b></div>
    <progress max={100} value={progress} aria-label="检测进度"/>
    {!completed && job.state !== 'failed' && <p className="muted">{job.frame != null ? `已处理 ${job.frame} / ${job.total_frames ?? '—'} 帧 · ` : ''}{progress >= 95 || job.eta_seconds == null ? '剩余时间估算中' : `预计剩余 ${seconds(job.eta_seconds)}`}</p>}
    {job.error && <Notice text={job.error}/>}
    <div className="result-grid"><Player path={path} version={job.finished_at_ts || job.job_id} title="公鹿检测完整视频"/>
      <div><div className={`qwen ${job.result?.conclusion?.includes('异常') && !noCandidates ? 'abnormal' : ''}`}><div className="section-heading"><h3>Qwen-VL 结论</h3><Badge value={noCandidates ? '未复核' : job.result?.conclusion || '待复核'}/></div><div className="confidence"><span>置信度</span><b>{noCandidates ? '—' : confidence(job.result?.confidence)}</b></div><p>{noCandidates ? '未触发候选事件，未进行 Qwen 复核。' : job.result?.evidence || (completed ? '未提供判断依据' : '等待模型返回结果')}</p></div>
      <div className="event-summary"><h3>候选事件摘要</h3><p>候选 <b>{job.event_count ?? events.length}</b> 个 · 判为异常（含疑似） <b>{events.filter(e => e.qwen_result?.conclusion?.includes('异常')).length}</b> 个</p><Link to={`/events?task_id=${encodeURIComponent(id)}`}>查看事件记录 <ArrowRight size={15}/></Link></div></div></div>
    {events.length > 0 && <details className="clips" onToggle={e => setClipsOpen(e.currentTarget.open)}><summary>候选片段与判断依据（{events.length}）</summary>{clipsOpen && <div className="clip-grid">{events.map((e, i) => <article key={e.event_id}><h3>候选事件 {i + 1} <small>{seconds(e.timestamp_seconds)}</small></h3><p className="muted">触发规则：{triggerLabel(e.reason)} · 行为未分类</p><Badge value={e.qwen_result?.conclusion}/><span className="muted"> 置信度 {confidence(e.qwen_result?.confidence)}</span><p>{e.qwen_result?.evidence || '未提供判断依据'}</p><Player path={e.video_url} version={job.finished_at_ts || id} title={`候选片段 ${i + 1}`}/></article>)}</div>}</details>}
  </>;
}
function Tasks() {
  const { data, error, loading, refresh } = useResource(api.history, 10000);
  const [search, setSearch] = useState(''); const [date, setDate] = useState(''); const [status, setStatus] = useState(''); const [page, setPage] = useState(1);
  const rows = (data || []).filter(t => `${t.task_id} ${t.filename}`.toLowerCase().includes(search.toLowerCase()) && (!date || t.created_at.startsWith(date)) && (!status || t.status === status));
  const actualPage = Math.min(page, Math.max(1, Math.ceil(rows.length / 10)));
  return <><PageTitle title="任务记录" subtitle="历史视频分析任务"><Link className="primary" to="/analyze"><Upload size={17}/>新建分析</Link></PageTitle>
    {error && <Notice text={error} retry={refresh}/>}
    <section><div className="filters"><label>任务 / 视频<input placeholder="搜索任务编号或视频名称" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}/></label><label>检测日期<input type="date" value={date} onChange={e => { setDate(e.target.value); setPage(1); }}/></label><label>任务状态<select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">全部状态</option><option value="queued">排队中</option><option value="processing">检测中</option><option value="completed">已完成</option><option value="failed">失败</option></select></label><button className="secondary" onClick={() => { setSearch(''); setDate(''); setStatus(''); setPage(1); }}>重置</button></div>
    {data?.length === 1000 && <p className="muted">当前显示最近 1000 条任务</p>}
    <div className="table-wrap"><table><thead><tr><th>视频 / 任务编号</th><th>创建时间</th><th>状态</th><th>候选事件</th><th>操作</th></tr></thead><tbody>{rows.slice((actualPage - 1) * 10, actualPage * 10).map(t => <tr key={t.task_id}><td><b>{t.filename}</b><small className="cell-sub">{t.task_id}</small>{t.error_message && <small className="danger-text">{t.error_message}</small>}</td><td>{t.created_at}</td><td><Badge value={t.status}/></td><td>{t.event_count}</td><td><div className="links"><Link to={`/analyze?task=${encodeURIComponent(t.task_id)}`}>任务详情</Link><Link to={`/events?task_id=${encodeURIComponent(t.task_id)}`}>事件记录</Link></div></td></tr>)}</tbody></table></div>{!rows.length && <Empty text={loading ? '正在加载…' : '没有符合条件的任务'}/>}<Pager page={actualPage} total={rows.length} onChange={setPage}/></section></>;
}
function Events() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo<EventFilters>(() => Object.fromEntries(['task_id', 'start_date', 'end_date', 'event_type', 'qwen_result'].map(k => [k, params.get(k) || undefined])), [params]);
  const page = Math.max(1, Number(params.get('page')) || 1);
  const load = useCallback((s: AbortSignal) => api.events(filters, page, s), [filters, page]);
  const { data, loading, error, refresh } = useResource(load);
  const types = useResource(api.types);
  const [invalid, setInvalid] = useState('');
  return <><PageTitle title="行为事件" subtitle="历史查询与候选片段回放"/>{error && <Notice text={error} retry={refresh}/>}
    <section><form className="filters" key={params.toString()} onSubmit={e => {
      e.preventDefault(); const form = new FormData(e.currentTarget); const start = String(form.get('start_date') || ''); const end = String(form.get('end_date') || '');
      if (start && end && start > end) { setInvalid('开始日期不能晚于结束日期'); return; }
      setInvalid(''); const next = new URLSearchParams(); form.forEach((v, k) => { if (v) next.set(k, String(v)); }); setParams(next);
    }}><label>任务编号<input name="task_id" defaultValue={filters.task_id} placeholder="输入完整任务编号"/></label><label>开始日期<input type="date" name="start_date" defaultValue={filters.start_date}/></label><label>结束日期<input type="date" name="end_date" defaultValue={filters.end_date}/></label><label>候选触发类型<select name="event_type" defaultValue={filters.event_type || ''}><option value="">全部类型</option>{[...new Set([...(types.data || []).map(t => t.event_type), ...(filters.event_type ? [filters.event_type] : [])])].map(t => <option key={t} value={t}>{triggerLabel(t)}</option>)}</select></label><label>Qwen 结论<select name="qwen_result" defaultValue={filters.qwen_result || ''}><option value="">全部结论</option>{['正常', '异常', '待复核', '复核失败'].map(t => <option key={t}>{t}</option>)}</select></label><button className="primary" type="submit">查询</button><button className="secondary" type="button" onClick={() => { setParams({}); setInvalid(''); }}>重置</button></form>
    {invalid && <Notice text={invalid}/>}
    <div className="section-heading"><h2>事件记录</h2><span className="muted">行为类别未标注 · 按触发规则统计</span></div>
    <div className="table-wrap" aria-busy={loading}><table><thead><tr><th>事件 / 任务</th><th>记录时间</th><th>片段时间</th><th>候选触发类型</th><th>检测置信度</th><th>Qwen 结论</th><th>Qwen 置信度</th><th>操作</th></tr></thead><tbody>{!loading && data?.events.map(e => <tr key={e.id}><td><b>事件 #{e.id}</b><Link className="cell-sub" to={`/analyze?task=${encodeURIComponent(e.task_id)}`}>{e.task_id}</Link></td><td>{e.created_at}</td><td>{seconds(e.start_time)} – {seconds(e.end_time)}</td><td>{triggerLabel(e.event_type)}</td><td>{confidence(e.confidence)}</td><td><Badge value={e.qwen_result}/></td><td>{confidence(e.qwen_confidence)}</td><td><Link to={`/events/${e.id}`}>查看回放</Link></td></tr>)}</tbody></table></div>{loading ? <Empty text="正在查询…"/> : !data?.events.length && <Empty text="没有符合条件的事件"/>}<Pager page={page} total={data?.total || 0} onChange={p => { const next = new URLSearchParams(params); next.set('page', String(p)); setParams(next); }}/></section></>;
}
function EventDetail() {
  const { eventId = '' } = useParams();
  const load = useCallback(async (s: AbortSignal) => {
    const event = await api.event(eventId, s);
    let job: Task | undefined;
    try { job = await api.job(event.task_id, s); } catch { /* History outlives the task JSON. */ }
    return { event, job };
  }, [eventId]);
  const { data, error, refresh } = useResource(load);
  const event = data?.event; const result = data?.job?.events?.[Math.max(0, (event?.event_index || 1) - 1)]?.qwen_result;
  return <><PageTitle title={`事件回放${event ? ` #${event.id}` : ''}`}><Link className="secondary" to={`/events${event ? '?task_id=' + encodeURIComponent(event.task_id) : ''}`}>返回事件记录</Link></PageTitle>{error && <Notice text={error} retry={refresh}/>}{event ? <section><div className="result-grid"><Player path={event.clip_url} version={event.created_at} title="候选事件片段"/><div className="event-facts"><h2>事件详情</h2><dl><dt>关联任务</dt><dd><Link to={`/analyze?task=${encodeURIComponent(event.task_id)}`}>{event.task_id}</Link></dd><dt>记录时间</dt><dd>{event.created_at}</dd><dt>片段时间</dt><dd>{seconds(event.start_time)} – {seconds(event.end_time)}</dd><dt>行为类型</dt><dd>未分类</dd><dt>候选触发规则</dt><dd>{triggerLabel(event.event_type)}</dd><dt>检测置信度</dt><dd>{confidence(event.confidence)}</dd><dt>Qwen 结论</dt><dd><Badge value={event.qwen_result}/></dd><dt>Qwen 置信度</dt><dd>{confidence(event.qwen_confidence)}</dd></dl><h3>判断依据</h3><p>{result?.evidence || '历史接口未保存判断依据，且未取得对应任务的详细结果。'}</p></div></div></section> : !error && <Empty text="正在读取事件…"/>}</>;
}
