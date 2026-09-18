package com.deer.mq;
import com.deer.config.RabbitConfig;
import com.deer.service.TaskStateService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.core.Message;
import org.springframework.stereotype.Component;
import com.rabbitmq.client.Channel;
@Component
public class RetryRouter {
    private final TaskStateService states;private final TaskPublisher sender;private final ObjectMapper json;
    public RetryRouter(TaskStateService s,TaskPublisher p,ObjectMapper j) {states=s;sender=p;json=j;}
    @RabbitListener(queues=RabbitConfig.FAIL)
    public void route(Message message,Channel channel) throws Exception {
        long tag=message.getMessageProperties().getDeliveryTag();
        try {
            String disposition;
            try {
                var body=json.readTree(message.getBody());
                if(!body.hasNonNull("taskId")) disposition="DLQ";
                else disposition=states.retryDisposition(body.get("taskId").asText());
            } catch(org.springframework.web.server.ResponseStatusException e) {
                if(e.getStatusCode().value()!=404) throw e;
                disposition="DLQ";
            } catch(com.fasterxml.jackson.core.JsonProcessingException e) { disposition="DLQ"; }
            if(!disposition.equals("SKIP")) sender.send(disposition.equals("DLQ")?"dead":"retry",message);
            channel.basicAck(tag,false);
        } catch(Exception e) {
            channel.basicNack(tag,false,true);
            Thread.sleep(1000);
        }
    }
}
