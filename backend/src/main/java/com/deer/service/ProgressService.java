package com.deer.service;
import com.deer.entity.*;
import org.springframework.stereotype.Service;
import org.springframework.data.redis.core.StringRedisTemplate;
import java.util.*;
import java.time.Duration;
import org.slf4j.*;
@Service
public class ProgressService {
    private final StringRedisTemplate redis;
    private static final Logger log=LoggerFactory.getLogger(ProgressService.class);
    public ProgressService(StringRedisTemplate redis) { this.redis=redis; }
    public String key(String id) { return "deer:task:"+id; }
    // Invoked under the task's DB row lock; Redis is a cache, never the state authority.
    public void write(String id,TaskStatus status,int progress,String stage,long frames,long total) {
        try {
            redis.opsForHash().putAll(key(id),Map.of("status",status.name(),"progress",String.valueOf(progress),"stage",stage,
                "processedFrames",String.valueOf(frames),"totalFrames",String.valueOf(total),"updatedAt",java.time.Instant.now().toString()));
            if(status.terminal()) redis.expire(key(id),Duration.ofHours(24)); else redis.persist(key(id));
        } catch(RuntimeException e) { log.warn("Redis unavailable for task {}: {}",id,e.getClass().getSimpleName()); }
    }
    public Map<String,Object> read(AnalysisTask task) {
        Map<String,Object> result=new HashMap<>();
        try { redis.opsForHash().entries(key(task.taskId)).forEach((k,v)->result.put(k.toString(),v)); } catch(RuntimeException ignored) {}
        result.put("status",task.getStatus().name());
        result.putIfAbsent("progress",0); result.putIfAbsent("stage",task.getStatus().name());
        result.putIfAbsent("processedFrames",0); result.putIfAbsent("totalFrames",0);
        if(task.getStatus()==TaskStatus.COMPLETED) result.put("progress",100);
        if(task.getStatus().terminal()) {
            result.put("stage",task.getStatus().name());
            // Repair a missed terminal cache write after Redis recovers.
            try {
                if(!task.getStatus().name().equals(redis.opsForHash().get(key(task.taskId),"status"))) {
                    write(task.taskId,task.getStatus(),task.getStatus()==TaskStatus.COMPLETED?100:0,task.getStatus().name(),0,0);
                } else if(redis.getExpire(key(task.taskId)) < 0) redis.expire(key(task.taskId),Duration.ofHours(24));
            } catch(RuntimeException ignored) {}
        }
        return result;
    }
}
