package com.deer.config;
import org.springframework.amqp.core.*;
import org.springframework.context.annotation.*;
import org.springframework.beans.factory.annotation.Value;
@Configuration
public class RabbitConfig {
    public static final String EX="deer.task.exchange", QUEUE="deer.task.queue", KEY="deer.task.analyze";
    public static final String FAIL_EX="deer.task.failure.exchange", FAIL="deer.task.failure.queue";
    public static final String RETRY="deer.task.retry.queue", DLQ="deer.task.dlq";
    @Bean Declarables topology(@Value("${deer.retry-delay-ms}") int delay) {
        DirectExchange main=new DirectExchange(EX,true,false), failure=new DirectExchange(FAIL_EX,true,false);
        Queue work=QueueBuilder.durable(QUEUE).deadLetterExchange(FAIL_EX).deadLetterRoutingKey("failure").build();
        Queue fail=QueueBuilder.durable(FAIL).build();
        Queue retry=QueueBuilder.durable(RETRY).ttl(delay).deadLetterExchange(EX).deadLetterRoutingKey(KEY).build();
        Queue dlq=QueueBuilder.durable(DLQ).build();
        return new Declarables(main,failure,work,fail,retry,dlq,
            BindingBuilder.bind(work).to(main).with(KEY),BindingBuilder.bind(fail).to(failure).with("failure"),
            BindingBuilder.bind(retry).to(main).with("retry"),BindingBuilder.bind(dlq).to(main).with("dead"));
    }
}
