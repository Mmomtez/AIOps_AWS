def observation_to_features(observation):
    metrics = observation.metrics

    return {
        "cpu": metrics.cpu,
        "memory": metrics.memory,
        "network_in": metrics.network_in,
        "network_out": metrics.network_out,
        "volume_write_bytes": metrics.volume_write_bytes,
        "raw_log_count": observation.raw_log_count,
        "error_count": observation.log_summary.error_count,
        "warning_count": observation.log_summary.warning_count,
    }