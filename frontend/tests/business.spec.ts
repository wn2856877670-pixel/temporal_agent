import { test, expect } from '@playwright/test';
const task = {taskId:'test-id',fileName:'spring.mp4',status:'RUNNING',eventCount:0,createdAt:'2026-09-18T10:00:00'};
const event = {id:1,eventId:'event-id',taskId:'test-id',eventIndex:1,eventType:'any_pair_iou',startTime:0,endTime:3,duration:3,qwenResult:'异常',qwenConfidence:.75,createdAt:'2026-09-18T10:00:00',evidence:'测试判断依据'};
test('Spring upload, progress and terminal polling stop, events and dashboard',async({page})=>{
  let done=false;let detailCalls=0;
  await page.route('**/api/**',route=>{
    const url=new URL(route.request().url());const path=url.pathname;
    const current=done?{...task,status:'COMPLETED',eventCount:1,resultJson:JSON.stringify({conclusion:'异常',confidence:.75,evidence:'测试判断依据'})}:task;
    if(path==='/api/tasks') return route.fulfill({json:route.request().method()==='POST'?current:{tasks:[current],total:1}});
    if(path==='/api/tasks/test-id') {detailCalls++;return route.fulfill({json:current});}
    if(path.endsWith('/progress')) return route.fulfill({json:{status:'RUNNING',progress:40,stage:'DETECTING',processedFrames:4,totalFrames:10}});
    if(path.endsWith('/events') && path.startsWith('/api/tasks/')) return route.fulfill({json:done?[event]:[]});
    if(path==='/api/events') return route.fulfill({json:{events:[event],total:1,page:1,pageSize:10}});
    if(path==='/api/events/1') return route.fulfill({json:event});
    if(path.endsWith('/overview')) return route.fulfill({json:{total_tasks:1,total_events:1,total_abnormal:1,today_tasks:1,today_events:1,today_abnormal:1}});
    if(path.endsWith('/daily')) return route.fulfill({json:[{date:'2026-09-18',count:1}]});
    return route.fulfill({json:[{event_type:'any_pair_iou',count:1}]});
  });
  await page.goto('/analyze');
  await page.getByLabel('选择视频').setInputFiles({name:'spring.mp4',mimeType:'video/mp4',buffer:Buffer.from('fixture')});
  const upload=page.waitForRequest(r=>r.url().endsWith('/api/tasks')&&r.method()==='POST');
  await page.getByRole('button',{name:'开始分析'}).click();await upload;
  await expect(page.getByText('40%',{exact:true}).first()).toBeVisible();
  done=true;
  await expect(page.getByText('测试判断依据',{exact:true}).first()).toBeVisible();
  await page.waitForTimeout(2200);const count=detailCalls;
  await page.waitForTimeout(2500);expect(detailCalls).toBe(count);
  await page.goto('/events');await page.getByLabel('开始日期').fill('2026-09-18');
  const filter=page.waitForRequest(r=>r.url().includes('startDate=2026-09-18'));
  await page.getByRole('button',{name:'查询',exact:true}).click();await filter;
  await page.getByRole('link',{name:'查看回放'}).click();
  await expect(page.getByText('测试判断依据',{exact:true})).toBeVisible();
  await page.goto('/dashboard');await expect(page.locator('.chart canvas')).toHaveCount(2);
});
