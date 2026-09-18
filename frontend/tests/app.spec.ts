import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const event = { id: 1, task_id: 'task-one', event_index: 1, event_type: 'any_pair_iou', start_time: 5, end_time: 20, confidence: .85, qwen_result: '异常', qwen_confidence: .75, clip_url: '/media/clip.webm', created_at: '2026-09-17 10:00:00' };
const task = { job_id: 'task-one', original_name: 'sample.mp4', state: 'completed', progress: 100, event_count: 1, created_at: '2026-09-17 10:00:00', finished_at_ts: 1789000000, processed_video_url: '/media/full.webm', result: { conclusion: '异常', confidence: .75, evidence: '观察到近距离接触' }, events: [{ event_id: 'one', timestamp_seconds: 10, reason: 'any_pair_iou', video_url: '/media/clip.webm', qwen_result: { conclusion: '异常', confidence: .75, evidence: '观察到近距离接触' } }] };
async function mockApi(page: Page) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    let body: unknown;
    if (url.pathname === '/api/jobs') body = route.request().method() === 'POST' ? { job: task } : { jobs: [task] };
    else if (url.pathname.startsWith('/api/jobs/')) body = task;
    else if (url.pathname === '/api/history/tasks') body = { tasks: [{ task_id: task.job_id, filename: task.original_name, status: 'completed', created_at: task.created_at, event_count: 1 }] };
    else if (url.pathname === '/api/history/events') body = { events: [event], total: 21, page: Number(url.searchParams.get('page') || 1), page_size: 10 };
    else if (url.pathname.startsWith('/api/history/events/')) body = event;
    else if (url.pathname.endsWith('/overview')) body = { total_tasks: 23, total_events: 196, total_abnormal: 172, today_tasks: 2, today_events: 4, today_abnormal: 3 };
    else if (url.pathname.endsWith('/daily')) body = Array.from({ length: 7 }, (_, i) => ({ date: `2026-09-${11 + i}`, count: i * 2 }));
    else body = [{ event_type: 'any_pair_iou', count: 196 }];
    await route.fulfill({ json: body });
  });
}
test.beforeEach(async ({ page }) => { await mockApi(page); });

test('dashboard charts, routes and desktop/mobile layout', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('/dashboard');
  await expect(page.getByText('196', { exact: true })).toBeVisible();
  await expect(page.locator('.chart canvas')).toHaveCount(2);
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true });
  await page.getByRole('link', { name: '任务记录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '任务记录' })).toBeVisible();
  await page.reload(); await expect(page.getByText('sample.mp4', { exact: true })).toBeVisible();
  await page.goto('/analyze?task=task-one');
  await expect(page.locator('video').first()).toHaveAttribute('src', /full.webm\?v=1789000000/);
  await page.screenshot({ path: 'test-results/analyze-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: '打开导航' }).click();
  await page.getByRole('link', { name: '数据看板', exact: true }).click();
  await page.screenshot({ path: 'test-results/dashboard-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('upload creates task and displays server progress then completion', async ({ page }) => {
  let running = true;
  await page.route('**/api/jobs/task-one', route => route.fulfill({ json: running ? { ...task, state: 'running', progress: 73, result: {}, events: [], processed_video_url: '' } : task }));
  await page.goto('/analyze');
  await page.getByLabel('选择视频').setInputFiles({ name: 'test.mp4', mimeType: 'video/mp4', buffer: Buffer.from('test-upload-fixture') });
  const request = page.waitForRequest(r => r.url().endsWith('/api/jobs') && r.method() === 'POST');
  await page.getByRole('button', { name: '开始分析' }).click();
  expect((await request).postData()).toContain('name="video"');
  await expect(page.getByRole('status').filter({ hasText: '任务已提交' })).toBeVisible();
  await expect(page.getByText('73%', { exact: true })).toBeVisible();
  await expect(page.locator('video')).toHaveCount(0);
  running = false;
  await expect(page.locator('video')).toHaveCount(1, { timeout: 10000 });
  await expect(page.getByText('观察到近距离接触', { exact: true }).first()).toBeVisible();
});

test('history filters are sent to server, pagination and event replay', async ({ page }) => {
  await page.goto('/events');
  await page.getByLabel('任务编号').fill('task-one');
  await page.getByLabel('开始日期').fill('2026-09-11');
  await page.getByLabel('候选触发类型').selectOption('any_pair_iou');
  const query = page.waitForRequest(r => r.url().includes('start_date=2026-09-11'));
  await page.getByRole('button', { name: '查询', exact: true }).click();
  expect((await query).url()).toContain('task_id=task-one');
  await expect(page.getByRole('link', { name: '查看回放' })).toBeVisible();
  const paged = page.waitForRequest(r => r.url().includes('page=2'));
  await page.getByRole('button', { name: '下一页' }).click(); await paged;
  await page.getByRole('link', { name: '查看回放' }).click();
  await expect(page.getByRole('heading', { name: '事件回放 #1' })).toBeVisible();
  await expect(page.getByText('观察到近距离接触', { exact: true })).toBeVisible();
  await expect(page.locator('video')).toHaveAttribute('src', /clip.webm\?v=/);
  await page.screenshot({ path: 'test-results/event-replay.png', fullPage: true });
});

test('empty, failed API, failed task and zero-candidate video', async ({ page }) => {
  await page.route('**/api/history/tasks**', route => route.fulfill({ json: { tasks: [] } }));
  await page.goto('/tasks'); await expect(page.getByText('没有符合条件的任务')).toBeVisible();
  await page.route('**/api/jobs/task-one', route => route.fulfill({ json: { ...task, events: [], event_count: 0 } }));
  await page.goto('/analyze?task=task-one');
  await expect(page.getByText('未触发候选事件，未进行 Qwen 复核。')).toBeVisible();
  await expect(page.locator('video')).toHaveCount(1);
  await page.route('**/api/jobs/task-one', route => route.fulfill({ json: { ...task, state: 'failed', error: '模型加载失败' } }));
  await page.reload(); await expect(page.getByRole('alert')).toContainText('模型加载失败');
  await page.route('**/api/statistics/**', route => route.fulfill({ status: 503, json: {} }));
  await page.goto('/dashboard'); await expect(page.getByRole('alert')).toContainText('服务连接失败');
});

test('video metadata and playback, stable node during polling, reload on failure', async ({ page }) => {
  const bytes = readFileSync('tests/playback.webm');
  await page.route('**/media/**', route => {
    const range = route.request().headers()['range'];
    const buffer = Buffer.from(bytes);
    if (!range) return route.fulfill({ contentType: 'video/webm', body: buffer });
    const match = /bytes=(\d+)-(\d*)/.exec(range)!;
    const start = Number(match[1]); const end = Math.min(Number(match[2] || buffer.length - 1), buffer.length - 1);
    return route.fulfill({ status: 206, headers: { 'Content-Type': 'video/webm', 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${buffer.length}` }, body: buffer.subarray(start, end + 1) });
  });
  await page.goto('/analyze?task=task-one');
  const video = page.locator('video').first();
  await video.waitFor();
  await expect.poll(() => video.evaluate(v => (v as HTMLVideoElement).readyState)).toBeGreaterThan(0);
  await video.evaluate(async v => { const el = v as HTMLVideoElement; el.muted = true; el.loop = true; await el.play(); el.dataset.preserved = 'yes'; });
  await expect.poll(() => video.evaluate(v => (v as HTMLVideoElement).currentTime)).toBeGreaterThan(0);
  await page.waitForTimeout(3300);
  await expect(video).toHaveAttribute('data-preserved', 'yes');
  await page.screenshot({ path: 'test-results/video-playing.png', fullPage: true });
  await page.route('**/media/**', route => route.fulfill({ status: 404 }));
  await page.getByRole('button', { name: '重新加载视频' }).click();
  await expect(page.getByRole('alert')).toContainText('视频加载失败');
});
