"""Memory usage monitoring for Mac M1."""

import gc
import resource


def get_memory_usage_gb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss / (1024 * 1024)


def check_memory_limit(max_gb: float) -> bool:
    current = get_memory_usage_gb()
    if current > max_gb:
        gc.collect()
        return False
    return True
