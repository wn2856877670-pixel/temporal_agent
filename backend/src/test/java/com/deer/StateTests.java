package com.deer;
import com.deer.entity.*;
import com.deer.repository.*;
import com.deer.service.*;
import com.deer.dto.WorkerDtos.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.web.server.ResponseStatusException;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
@DataJpaTest(properties={"spring.jpa.hibernate.ddl-auto=create-drop", "deer.lease-seconds=120"})
@Import({TaskStateService.class,TaskService.class,MediaService.class,StateTests.Config.class})
class StateTests {
    @TempDir static Path root;
    @DynamicPropertySource static void properties(DynamicPropertyRegistry r) {r.add("deer.media-root",()->root.toString());}
    @TestConfiguration static class Config {@Bean ObjectMapper json(){return new ObjectMapper();}}
    @MockitoBean ProgressService progress;
    @Autowired TaskRepository tasks;
    @Autowired EventRepository events;
    @Autowired TaskStateService states;
    @Autowired TaskService service;
    String create() {
        AnalysisTask t=new AnalysisTask();t.taskId=UUID.randomUUID().toString();t.fileName="test.mp4";t.videoPath="/input.mp4";tasks.saveAndFlush(t);return t.taskId;
    }
    @Test void terminalNeverRollsBack() throws Exception {
        String id=create();var claim=states.claim(id,"test");String token=(String)claim.get("leaseToken");
        assertFalse((Boolean)states.claim(id,"duplicate").get("claimed"));
        assertThrows(ResponseStatusException.class,()->states.status(id,token,new Status(TaskStatus.COMPLETED,null,null,null)));
        assertThrows(ResponseStatusException.class,()->states.status(id,"stale",new Status(TaskStatus.REVIEWING,null,null,null)));
        states.status(id,token,new Status(TaskStatus.REVIEWING,null,null,null));
        Path clip=root.resolve("results").resolve(id).resolve("result.mp4");Files.createDirectories(clip.getParent());Files.write(clip,new byte[]{1});
        Event e=new Event(1,"test",0,1,null,null,null,"正常",0.8,clip.toString(),"test");
        service.archive(id,token,List.of(e));service.archive(id,token,List.of(e));
        assertEquals(1,events.countByTaskId(id));
        states.status(id,token,new Status(TaskStatus.COMPLETED,null,clip.toString(),Map.of()));
        assertTrue((Boolean)states.claim(id,"duplicate").get("alreadyCompleted"));
        assertThrows(ResponseStatusException.class,()->states.status(id,token,new Status(TaskStatus.RUNNING,null,null,null)));
        assertEquals(TaskStatus.COMPLETED,states.get(id).getStatus());
    }
    @Test void retryFencesPreviousOwnerAndCapsAtFourExecutions() {
        String id=create();String old=(String)states.claim(id,"a").get("leaseToken");
        states.release(id,old,"failure");
        for(int i=2;i<=4;i++) {
            var c=states.claim(id,"next");assertEquals(i,c.get("attempt"));
            assertThrows(ResponseStatusException.class,()->states.heartbeat(id,old,new Progress(10,"test",1,10)));
            states.release(id,(String)c.get("leaseToken"),"failure");
        }
        assertEquals("DLQ",states.retryDisposition(id));assertEquals(TaskStatus.FAILED,states.get(id).getStatus());
    }
    @Test void transitionMatrix() {
        for(TaskStatus from:TaskStatus.values()) for(TaskStatus to:TaskStatus.values()) {
            boolean expected=!from.terminal() && (to==TaskStatus.FAILED || from==TaskStatus.QUEUED&&to==TaskStatus.RUNNING || from==TaskStatus.RUNNING&&to==TaskStatus.REVIEWING || from==TaskStatus.REVIEWING&&to==TaskStatus.COMPLETED);
            assertEquals(expected,from.allows(to));
        }
    }
}
