package com.deer.controller;
import com.deer.entity.*;
import com.deer.repository.*;
import com.deer.service.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.data.domain.*;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.time.*;
import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
@RestController @RequestMapping("/api")
public class QueryController {
    private final TaskRepository tasks;private final EventRepository events;private final TaskService service;
    private final TaskStateService states;private final ProgressService progress;private final MediaService media;private final ObjectMapper json;
    public QueryController(TaskRepository t,EventRepository e,TaskService s,TaskStateService st,ProgressService p,MediaService m,ObjectMapper j) {tasks=t;events=e;service=s;states=st;progress=p;media=m;json=j;}
    private Map<String,Object> task(AnalysisTask t) {
        Map<String,Object> result=json.convertValue(t,new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
        result.put("outputUrl",media.url(t.resultVideoPath));return result;
    }
    private Map<String,Object> event(BehaviorEvent e) {
        Map<String,Object> result=json.convertValue(e,new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
        result.put("clipUrl",media.url(e.clipPath));return result;
    }
    private Pageable pageable(int page,int size) {if(page<1 || size<1 || size>1000) throw new IllegalArgumentException("Invalid pagination");return PageRequest.of(page-1,size,Sort.by(Sort.Direction.DESC,"createdAt","id"));}
    @PostMapping("/tasks") @ResponseStatus(HttpStatus.ACCEPTED)
    public Object upload(@RequestParam("video") MultipartFile video) throws Exception {return task(service.upload(video));}
    @GetMapping("/tasks/{id}") public Object task(@PathVariable String id) {return task(states.get(id));}
    @GetMapping("/tasks/{id}/progress") public Object progress(@PathVariable String id) {return progress.read(states.get(id));}
    @GetMapping("/tasks/{id}/events") public Object taskEvents(@PathVariable String id) {states.get(id);return events.findByTaskIdOrderByEventIndex(id).stream().map(this::event).toList();}
    @GetMapping("/tasks") public Object tasks(@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="50") int pageSize,
        @RequestParam(required=false) String taskId,@RequestParam(required=false) TaskStatus status,
        @RequestParam(required=false) LocalDate startDate,@RequestParam(required=false) LocalDate endDate) {
        validateDates(startDate,endDate);
        Specification<AnalysisTask> spec=(r,q,b)->b.conjunction();
        if(taskId!=null) spec=spec.and((r,q,b)->b.equal(r.get("taskId"),taskId));
        if(status!=null) spec=spec.and((r,q,b)->b.equal(r.get("status"),status));
        if(startDate!=null) spec=spec.and((r,q,b)->b.greaterThanOrEqualTo(r.get("createdAt"),startDate.atStartOfDay()));
        if(endDate!=null) spec=spec.and((r,q,b)->b.lessThan(r.get("createdAt"),endDate.plusDays(1).atStartOfDay()));
        var data=tasks.findAll(spec,pageable(page,pageSize));return Map.of("tasks",data.stream().map(this::task).toList(),"total",data.getTotalElements(),"page",page,"pageSize",pageSize);
    }
    private void validateDates(LocalDate start,LocalDate end) {if(start!=null && end!=null && start.isAfter(end)) throw new IllegalArgumentException("Invalid date range");}
    @GetMapping("/events") public Object events(@RequestParam(defaultValue="1") int page,@RequestParam(defaultValue="10") int pageSize,
        @RequestParam(required=false) String taskId,@RequestParam(required=false) String eventType,@RequestParam(required=false) String qwenResult,
        @RequestParam(required=false) LocalDate startDate,@RequestParam(required=false) LocalDate endDate) {
        validateDates(startDate,endDate);
        Specification<BehaviorEvent> spec=(r,q,b)->b.conjunction();
        if(taskId!=null) spec=spec.and((r,q,b)->b.equal(r.get("taskId"),taskId));
        if(eventType!=null) spec=spec.and((r,q,b)->b.equal(r.get("eventType"),eventType));
        if(qwenResult!=null) spec=spec.and((r,q,b)->b.equal(r.get("qwenResult"),qwenResult));
        if(startDate!=null) spec=spec.and((r,q,b)->b.greaterThanOrEqualTo(r.get("createdAt"),startDate.atStartOfDay()));
        if(endDate!=null) spec=spec.and((r,q,b)->b.lessThan(r.get("createdAt"),endDate.plusDays(1).atStartOfDay()));
        var data=events.findAll(spec,pageable(page,pageSize));return Map.of("events",data.stream().map(this::event).toList(),"total",data.getTotalElements(),"page",page,"pageSize",pageSize);
    }
    @GetMapping("/events/{id}") public Object event(@PathVariable Long id) {return event(events.findById(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Event not found")));}
    private Specification<BehaviorEvent> onDay(LocalDate date) {return (r,q,b)->b.and(b.greaterThanOrEqualTo(r.get("createdAt"),date.atStartOfDay()),b.lessThan(r.get("createdAt"),date.plusDays(1).atStartOfDay()));}
    private Specification<BehaviorEvent> abnormal() {return (r,q,b)->b.or(b.like(r.get("qwenResult"),"%异常%"),b.like(r.get("qwenResult"),"%疑似%"));}
    @GetMapping("/statistics/overview") public Object overview() {
        var day=LocalDate.now();
        long today=tasks.count((r,q,b)->b.and(b.greaterThanOrEqualTo(r.get("createdAt"),day.atStartOfDay()),b.lessThan(r.get("createdAt"),day.plusDays(1).atStartOfDay())));
        return Map.of("total_tasks",tasks.count(),"total_events",events.count(),"total_abnormal",events.count(abnormal()),"today_tasks",today,"today_events",events.count(onDay(day)),"today_abnormal",events.count(onDay(day).and(abnormal())));
    }
    @GetMapping("/statistics/daily") public Object daily(@RequestParam(defaultValue="7") int days) {
        if(days<1 || days>366) throw new IllegalArgumentException("days must be 1..366");
        List<Object> rows=new ArrayList<>();for(int i=days-1;i>=0;i--) {var day=LocalDate.now().minusDays(i);rows.add(Map.of("date",day.toString(),"count",events.count(onDay(day))));}return rows;
    }
    @GetMapping("/statistics/event-types") public Object types() {return events.countTypes().stream().map(r->Map.of("event_type",r[0]==null?"unclassified":r[0],"count",r[1])).toList();}
}
