package com.deer.service;
import com.deer.entity.*;
import com.deer.repository.*;
import com.deer.dto.WorkerDtos.Event;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import java.nio.file.*;
import java.util.*;
@Service
public class TaskService {
    private final TaskRepository tasks; private final OutboxRepository outbox; private final LogRepository logs;
    private final TaskStateService states; private final ProgressService progress; private final EventRepository events; private final MediaService media;
    public TaskService(TaskRepository t,OutboxRepository o,LogRepository l,TaskStateService s,ProgressService p,EventRepository e,MediaService m) {
        tasks=t;outbox=o;logs=l;states=s;progress=p;events=e;media=m;
    }
    @Transactional
    public AnalysisTask upload(MultipartFile video) throws Exception {
        String name=Optional.ofNullable(video.getOriginalFilename()).orElse("video.mp4").replace('\\','/');
        name=name.substring(name.lastIndexOf('/')+1);
        if(video.isEmpty() || name.length()>255 || !name.toLowerCase(Locale.ROOT).matches(".+\\.(mp4|avi|mov|mkv)$")) throw new IllegalArgumentException("Invalid video");
        AnalysisTask t=new AnalysisTask(); t.taskId=UUID.randomUUID().toString(); t.fileName=name;
        Path file=media.root.resolve("uploads").resolve(t.taskId).resolve("input"+name.substring(name.lastIndexOf('.')).toLowerCase(Locale.ROOT));
        Files.createDirectories(file.getParent());
        try(var stream=video.getInputStream()) { Files.copy(stream,file); }
        t.videoPath=file.toString(); tasks.save(t);
        TaskOutbox message=new TaskOutbox(); message.taskId=t.taskId; outbox.save(message);
        logs.save(new TaskLog(t.taskId,"QUEUED","INFO","Upload stored; durable outbox created"));
        progress.write(t.taskId,TaskStatus.QUEUED,0,"QUEUED",0,0);
        return t;
    }
    @Transactional
    public List<BehaviorEvent> archive(String id,String token,List<Event> input) {
        AnalysisTask task=states.lock(id); states.owned(task,token);
        if(task.getStatus()!=TaskStatus.REVIEWING) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.CONFLICT,"Events require REVIEWING");
        List<BehaviorEvent> result=new ArrayList<>();
        for(Event dto:input) {
            if(dto.endTime()<dto.startTime()) throw new IllegalArgumentException("Invalid event times");
            BehaviorEvent old=events.findByTaskIdAndEventIndex(id,dto.eventIndex()).orElse(null);
            if(old!=null) { result.add(old); continue; }
            BehaviorEvent e=new BehaviorEvent(); e.taskId=id;e.eventIndex=dto.eventIndex();e.eventId=UUID.randomUUID().toString();
            e.eventType=dto.eventType(); e.startTime=dto.startTime();e.endTime=dto.endTime();e.duration=e.endTime-e.startTime;
            e.maleTrackId=dto.maleTrackId();e.targetTrackId=dto.targetTrackId();e.confidence=dto.confidence();
            e.qwenResult=dto.qwenResult();e.qwenConfidence=dto.qwenConfidence();e.evidence=dto.evidence();e.clipPath=media.validate(dto.clipPath(),id);
            result.add(events.saveAndFlush(e));
        }
        task.eventCount=Math.toIntExact(events.countByTaskId(id));
        logs.save(new TaskLog(id,"ARCHIVE","INFO","Archived "+result.size()+" events (idempotent)"));
        return result;
    }
}
