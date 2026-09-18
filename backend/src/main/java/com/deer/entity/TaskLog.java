package com.deer.entity;
import jakarta.persistence.*;
import java.time.LocalDateTime;
@Entity @Table(name="task_log", indexes=@Index(name="ix_log_task",columnList="taskId,createdAt"))
public class TaskLog {
    @Id @GeneratedValue(strategy=GenerationType.IDENTITY) public Long id;
    @Column(nullable=false,length=64) public String taskId;
    public String stage, level;
    @Column(length=4000) public String message;
    public LocalDateTime createdAt=LocalDateTime.now();
    public TaskLog() {}
    public TaskLog(String task, String stage, String level, String message) {
        this.taskId=task; this.stage=stage; this.level=level; this.message=message;
    }
}
