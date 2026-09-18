package com.deer.mq;
import com.deer.config.RabbitConfig;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.core.*;
import org.springframework.stereotype.Component;
import java.util.concurrent.TimeUnit;
@Component
public class TaskPublisher {
    private final RabbitTemplate rabbit;
    public TaskPublisher(RabbitTemplate rabbit) { this.rabbit=rabbit; }
    public void send(String key,Message message) throws Exception {
        message.getMessageProperties().setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        CorrelationData confirm=new CorrelationData(java.util.UUID.randomUUID().toString());
        rabbit.send(RabbitConfig.EX,key,message,confirm);
        if(!confirm.getFuture().get(10,TimeUnit.SECONDS).isAck() || confirm.getReturned()!=null) throw new IllegalStateException("Rabbit publish not confirmed/routed");
    }
}
