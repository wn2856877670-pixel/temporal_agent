package com.deer.entity;
import jakarta.persistence.*;
import java.time.LocalDateTime;
@Entity @Table(name="behavior_event", uniqueConstraints=@UniqueConstraint(name="uq_task_event", columnNames={"taskId","eventIndex"}), indexes=@Index(name="ix_event_created",columnList="createdAt"))
public class BehaviorEvent {
    @Id @GeneratedValue(strategy=GenerationType.IDENTITY) public Long id;
    @Column(nullable=false, unique=true, length=64) public String eventId;
    @Column(nullable=false, length=64) public String taskId;
    @Column(nullable=false) public int eventIndex;
    @Column(length=100) public String eventType;
    public double startTime, endTime, duration;
    public Integer maleTrackId, targetTrackId;
    public Double confidence, qwenConfidence;
    @Column(length=100) public String qwenResult;
    @Column(length=1024) public String clipPath;
    @Column(columnDefinition="TEXT") public String evidence;
    public LocalDateTime createdAt = LocalDateTime.now();
}
