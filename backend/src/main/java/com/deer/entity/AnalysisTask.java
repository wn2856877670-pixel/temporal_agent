package com.deer.entity;
import jakarta.persistence.*;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.LocalDateTime;
@Entity @Table(name="analysis_task", indexes=@Index(name="ix_task_created", columnList="createdAt"))
public class AnalysisTask {
    @Id @GeneratedValue(strategy=GenerationType.IDENTITY) public Long id;
    @Column(nullable=false, unique=true, length=64) public String taskId;
    @Column(nullable=false) public String fileName;
    @Column(nullable=false, length=1024) public String videoPath;
    @Column(length=1024) public String resultVideoPath;
    @Enumerated(EnumType.STRING) @Column(nullable=false, length=20) private TaskStatus status = TaskStatus.QUEUED;
    public TaskStatus getStatus() { return status; }
    public int eventCount;
    @Column(length=4000) public String errorMessage;
    public LocalDateTime createdAt = LocalDateTime.now(), startedAt, finishedAt;
    @JsonIgnore public String leaseToken;
    @JsonIgnore public LocalDateTime leaseUntil;
    public int attempts;
    @Column(columnDefinition="TEXT") public String resultJson;
}
