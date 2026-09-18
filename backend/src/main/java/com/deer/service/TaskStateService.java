package com.deer.service;
import com.deer.entity.*;
import com.deer.repository.*;
import com.deer.dto.WorkerDtos.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.time.LocalDateTime;
import java.util.*;
@Service
public class TaskStateService {
    private final TaskRepository tasks; private final EventRepository events; private final LogRepository logs;
    private final ProgressService progress; private final EntityManager em; private final MediaService media;
    private final ObjectMapper json; private final int leaseSeconds;
    public TaskStateService(TaskRepository t,EventRepository e,LogRepository l,ProgressService p,EntityManager em,MediaService m,ObjectMapper j,@Value("${deer.lease-seconds}") int lease) {
        tasks=t; events=e; logs=l; progress=p; this.em=em; media=m; json=j; leaseSeconds=lease;
    }
    public AnalysisTask get(String id) { return tasks.findByTaskId(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Task not found")); }
    public AnalysisTask lock(String id) { return tasks.lock(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Task not found")); }
    public void owned(AnalysisTask t,String token) {
        if(token==null || !token.equals(t.leaseToken) || t.leaseUntil==null || t.leaseUntil.isBefore(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Worker lease expired or fenced");
    }
    private void transition(AnalysisTask t,TaskStatus next) {
        TaskStatus previous=t.getStatus();
        if(!previous.allows(next)) throw new ResponseStatusException(HttpStatus.CONFLICT,"Illegal transition: "+previous+" -> "+next);
        em.flush();
        if(tasks.transition(t.taskId,previous,next)!=1) throw new ResponseStatusException(HttpStatus.CONFLICT,"Concurrent transition");
        em.refresh(t);
        logs.save(new TaskLog(t.taskId,next.name(),"INFO",previous+" -> "+next));
    }
    @Transactional
    public Map<String,Object> claim(String id,String owner) {
        AnalysisTask t=lock(id);
        if(t.getStatus().terminal()) return Map.of("alreadyCompleted",t.getStatus()==TaskStatus.COMPLETED,"terminal",true,"claimed",false);
        if(t.leaseUntil!=null && t.leaseUntil.isAfter(LocalDateTime.now())) return Map.of("claimed",false,"busy",true);
        if(t.attempts>=4) { fail(t,"Retry limit exhausted"); return Map.of("claimed",false,"terminal",true); }
        if(t.getStatus()==TaskStatus.QUEUED) { transition(t,TaskStatus.RUNNING); t.startedAt=LocalDateTime.now(); }
        t.attempts++; t.leaseToken=UUID.randomUUID().toString(); t.leaseUntil=LocalDateTime.now().plusSeconds(leaseSeconds);
        logs.save(new TaskLog(id,"CLAIM","INFO","Attempt "+t.attempts+" owner="+owner));
        progress.write(id,t.getStatus(),0,"STARTING",0,0);
        return Map.of("claimed",true,"leaseToken",t.leaseToken,"attempt",t.attempts,"videoPath",t.videoPath,"fileName",t.fileName,"status",t.getStatus());
    }
    @Transactional
    public void heartbeat(String id,String token,Progress value) {
        AnalysisTask t=lock(id); owned(t,token);
        if(t.getStatus().terminal()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Task finished");
        t.leaseUntil=LocalDateTime.now().plusSeconds(leaseSeconds);
        progress.write(id,t.getStatus(),value.progress(),value.stage(),value.processedFrames(),value.totalFrames());
    }
    @Transactional
    public void release(String id,String token,String error) {
        AnalysisTask t=lock(id); owned(t,token);
        if(t.getStatus().terminal()) return;
        t.leaseUntil=LocalDateTime.now().minusSeconds(1); t.errorMessage=error;
        logs.save(new TaskLog(id,"RETRY","WARN",error));
    }
    @Transactional
    public AnalysisTask status(String id,String token,Status request) {
        AnalysisTask t=lock(id);
        // Idempotent response after a successful terminal commit but lost HTTP response.
        if(t.getStatus()==request.status() && t.getStatus().terminal() && Objects.equals(t.leaseToken,token)) return t;
        owned(t,token);
        if(request.status()==TaskStatus.RUNNING) throw new ResponseStatusException(HttpStatus.CONFLICT,"Use claim for RUNNING");
        if(t.getStatus()!=request.status()) {
            if(!t.getStatus().allows(request.status())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Illegal state transition");
            if(request.status()==TaskStatus.COMPLETED) {
                if(request.resultVideoPath()==null) throw new IllegalArgumentException("Completion requires result video");
                t.resultVideoPath=media.validate(request.resultVideoPath(),id);
                t.eventCount=Math.toIntExact(events.countByTaskId(id));
                try { t.resultJson=json.writeValueAsString(request.result()); } catch(Exception e) { throw new IllegalArgumentException("Invalid summary"); }
            }
            transition(t,request.status());
        }
        if(t.getStatus().terminal()) {
            t.finishedAt=LocalDateTime.now(); t.errorMessage=request.errorMessage();
            progress.write(id,t.getStatus(),t.getStatus()==TaskStatus.COMPLETED?100:0,t.getStatus().name(),0,0);
        } else { t.leaseUntil=LocalDateTime.now().plusSeconds(leaseSeconds); progress.write(id,t.getStatus(),90,"QWEN_REVIEW",0,0); }
        return t;
    }
    private void fail(AnalysisTask t,String error) {
        if(!t.getStatus().terminal()) { transition(t,TaskStatus.FAILED); t.errorMessage=error; t.finishedAt=LocalDateTime.now(); progress.write(t.taskId,TaskStatus.FAILED,0,"FAILED",0,0); }
    }
    @Transactional
    public String retryDisposition(String id) {
        AnalysisTask t=lock(id);
        if(t.getStatus()==TaskStatus.COMPLETED) return "SKIP";
        if(t.getStatus()==TaskStatus.FAILED) return "DLQ";
        if(t.leaseUntil!=null && t.leaseUntil.isAfter(LocalDateTime.now())) return "RETRY";
        if(t.attempts>=4) { fail(t,t.errorMessage==null?"Worker lost after maximum retries":t.errorMessage); return "DLQ"; }
        return "RETRY";
    }
}
