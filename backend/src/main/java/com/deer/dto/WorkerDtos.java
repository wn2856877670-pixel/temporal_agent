package com.deer.dto;
import com.deer.entity.TaskStatus;
import jakarta.validation.constraints.*;
import java.util.Map;
public final class WorkerDtos {
    public record Claim(@NotBlank @Size(max=64) String owner) {}
    public record Progress(@Min(0) @Max(99) int progress, @NotBlank @Size(max=80) String stage,
        @Min(0) long processedFrames, @Min(0) long totalFrames) {}
    public record Status(@NotNull TaskStatus status, @Size(max=4000) String errorMessage,
        @Size(max=1024) String resultVideoPath, Map<String,Object> result) {}
    public record Event(@Min(1) int eventIndex, @NotBlank @Size(max=100) String eventType,
        @DecimalMin("0") double startTime, @DecimalMin("0") double endTime,
        Integer maleTrackId,Integer targetTrackId,
        @DecimalMin("0") @DecimalMax("1") Double confidence,
        @NotBlank @Size(max=100) String qwenResult,
        @DecimalMin("0") @DecimalMax("1") Double qwenConfidence,
        @NotBlank @Size(max=1024) String clipPath, @Size(max=16000) String evidence) {}
}
