package com.deer.repository;
import com.deer.entity.*;
import org.springframework.data.jpa.repository.*;
import jakarta.persistence.LockModeType;
import java.util.*;
public interface TaskRepository extends JpaRepository<AnalysisTask,Long>, JpaSpecificationExecutor<AnalysisTask> {
    Optional<AnalysisTask> findByTaskId(String taskId);
    @Lock(LockModeType.PESSIMISTIC_WRITE) @Query("select t from AnalysisTask t where t.taskId=:id")
    Optional<AnalysisTask> lock(String id);
    @Modifying @Query("update AnalysisTask t set t.status=:next where t.taskId=:id and t.status=:expected")
    int transition(String id, TaskStatus expected, TaskStatus next);
}
