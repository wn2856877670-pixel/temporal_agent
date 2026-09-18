package com.deer.mq;
import com.deer.repository.*;
import com.deer.config.RabbitConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.time.LocalDateTime;
import java.util.Map;
import org.slf4j.*;
@Component
public class OutboxDispatcher {
    private final OutboxRepository outbox; private final TaskRepository tasks; private final TaskPublisher sender; private final ObjectMapper json;
    private final Logger log=LoggerFactory.getLogger(getClass());
    public OutboxDispatcher(OutboxRepository o,TaskRepository t,TaskPublisher p,ObjectMapper j) {outbox=o;tasks=t;sender=p;json=j;}
    @Scheduled(fixedDelay=2000)
    public void dispatch() {
        for(var item:outbox.findTop20BySentFalseAndNextAttemptBefore(LocalDateTime.now())) {
            try {
                var task=tasks.findByTaskId(item.taskId).orElseThrow();
                if(!task.getStatus().terminal()) {
                    MessageProperties props=new MessageProperties();props.setContentType("application/json");
                    sender.send(RabbitConfig.KEY,new Message(json.writeValueAsBytes(Map.of("taskId",task.taskId,"videoPath",task.videoPath)),props));
                }
                item.sent=true;
            } catch(Exception e) { item.nextAttempt=LocalDateTime.now().plusSeconds(10);log.warn("Outbox retry {}: {}",item.taskId,e.toString()); }
            outbox.save(item);
        }
    }
}
