package com.deer.repository;
import com.deer.entity.TaskOutbox;
import org.springframework.data.jpa.repository.JpaRepository;
import java.time.LocalDateTime;
import java.util.List;
public interface OutboxRepository extends JpaRepository<TaskOutbox,String> {
    List<TaskOutbox> findTop20BySentFalseAndNextAttemptBefore(LocalDateTime now);
}
