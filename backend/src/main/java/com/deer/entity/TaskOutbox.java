package com.deer.entity;
import jakarta.persistence.*;
import java.time.LocalDateTime;
@Entity @Table(name="task_outbox")
public class TaskOutbox {
    @Id @Column(length=64) public String taskId;
    public boolean sent;
    public LocalDateTime nextAttempt=LocalDateTime.now();
}
