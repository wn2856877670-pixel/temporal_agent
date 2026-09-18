package com.deer.repository;
import com.deer.entity.BehaviorEvent;
import org.springframework.data.jpa.repository.*;
import java.util.*;
public interface EventRepository extends JpaRepository<BehaviorEvent,Long>, JpaSpecificationExecutor<BehaviorEvent> {
    List<BehaviorEvent> findByTaskIdOrderByEventIndex(String taskId);
    Optional<BehaviorEvent> findByTaskIdAndEventIndex(String taskId,int index);
    long countByTaskId(String taskId);
    @Query("select e.eventType, count(e) from BehaviorEvent e group by e.eventType")
    List<Object[]> countTypes();
}
