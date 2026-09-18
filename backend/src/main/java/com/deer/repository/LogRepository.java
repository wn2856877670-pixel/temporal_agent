package com.deer.repository;
import com.deer.entity.TaskLog;
import org.springframework.data.jpa.repository.JpaRepository;
public interface LogRepository extends JpaRepository<TaskLog,Long> {}
