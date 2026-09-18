package com.deer.entity;
public enum TaskStatus {
    QUEUED, RUNNING, REVIEWING, COMPLETED, FAILED;
    public boolean terminal() { return this == COMPLETED || this == FAILED; }
    public boolean allows(TaskStatus next) {
        return !terminal() && (next == FAILED || this == QUEUED && next == RUNNING
            || this == RUNNING && next == REVIEWING || this == REVIEWING && next == COMPLETED);
    }
}
