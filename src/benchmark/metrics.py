"""Benchmark metrics and comparison."""

from dataclasses import dataclass, field

from src.models import BenchmarkResult, Event


@dataclass
class ComparisonMetrics:
    """Metrics comparing two benchmark runs."""
    
    fixed_result: BenchmarkResult
    event_result: BenchmarkResult
    
    @property
    def invocation_reduction(self) -> float:
        """Percentage reduction in invocations (event vs fixed)."""
        if self.fixed_result.total_invocations == 0:
            return 0.0
        reduction = 1 - (
            self.event_result.total_invocations / 
            self.fixed_result.total_invocations
        )
        return reduction * 100
    
    @property
    def fixed_invocation_rate(self) -> float:
        """Invocations per 100 frames for fixed trigger."""
        return self.fixed_result.invocation_rate
    
    @property
    def event_invocation_rate(self) -> float:
        """Invocations per 100 frames for event trigger."""
        return self.event_result.invocation_rate
    
    def summary(self) -> str:
        """Generate human-readable comparison summary."""
        lines = [
            "=" * 60,
            "BENCHMARK COMPARISON RESULTS",
            "=" * 60,
            "",
            f"Total frames processed: {self.fixed_result.total_frames}",
            "",
            "Fixed Interval Trigger:",
            f"  - Invocations: {self.fixed_result.total_invocations}",
            f"  - Rate: {self.fixed_invocation_rate:.2f}%",
            "",
            "Event-Driven Trigger:",
            f"  - Invocations: {self.event_result.total_invocations}",
            f"  - Rate: {self.event_invocation_rate:.2f}%",
            f"  - Events detected: {len(self.event_result.events_detected)}",
            "",
            f"Invocation Reduction: {self.invocation_reduction:.1f}%",
            "=" * 60,
        ]
        return "\n".join(lines)


def calculate_temporal_precision(
    detected_events: list[Event],
    ground_truth: list[dict],
    tolerance_seconds: float = 0.5,
) -> dict:
    """Calculate how precisely events were timestamped.
    
    Args:
        detected_events: Events from the tracker
        ground_truth: Ground truth events (from SyntheticVideoSource)
        tolerance_seconds: Maximum time difference for a match
        
    Returns:
        Dict with precision metrics
    """
    if not ground_truth:
        return {"precision": 1.0, "recall": 1.0, "matched": 0, "total_gt": 0}
    
    matched = 0
    for gt in ground_truth:
        gt_time = gt["timestamp"]
        gt_type = gt["type"]
        gt_object = gt["object"]
        
        for det in detected_events:
            det_type = det.event_type.value
            det_time = det.timestamp_seconds
            
            # Check if event types match
            type_match = (
                (gt_type == "object_enter" and det_type == "object_enter") or
                (gt_type == "object_exit" and det_type == "object_exit")
            )
            
            # Check object class
            object_match = gt_object in det.object_class
            
            # Check timing
            time_match = abs(gt_time - det_time) <= tolerance_seconds
            
            if type_match and object_match and time_match:
                matched += 1
                break
    
    precision = matched / len(detected_events) if detected_events else 0.0
    recall = matched / len(ground_truth)
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0,
        "matched": matched,
        "total_detected": len(detected_events),
        "total_gt": len(ground_truth),
    }
