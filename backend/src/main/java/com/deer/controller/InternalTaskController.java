package com.deer.controller;
import com.deer.service.*;
import com.deer.dto.WorkerDtos.*;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.validation.annotation.Validated;
import java.util.*;
@RestController @RequestMapping("/api/internal/tasks/{id}") @Validated
public class InternalTaskController {
    private final TaskStateService states; private final TaskService tasks;
    public InternalTaskController(TaskStateService s,TaskService t) {states=s;tasks=t;}
    @PostMapping("/claim") public Object claim(@PathVariable String id,@Valid @RequestBody Claim body) {return states.claim(id,body.owner());}
    @PatchMapping("/progress") public void progress(@PathVariable String id,@RequestHeader("X-Lease-Token") String token,@Valid @RequestBody Progress body) {states.heartbeat(id,token,body);}
    @PatchMapping("/status") public Object status(@PathVariable String id,@RequestHeader("X-Lease-Token") String token,@Valid @RequestBody Status body) {return states.status(id,token,body);}
    @PostMapping("/events") public Object events(@PathVariable String id,@RequestHeader("X-Lease-Token") String token,@RequestBody @Size(max=5000) List<@Valid Event> body) {return tasks.archive(id,token,body);}
    @PostMapping("/release") public void release(@PathVariable String id,@RequestHeader("X-Lease-Token") String token,@RequestBody Map<String,String> body) {states.release(id,token,body.getOrDefault("error","Worker failed").substring(0,Math.min(3900,body.getOrDefault("error","Worker failed").length())));}
}
