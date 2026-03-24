from backend.aws.cloudwatch_collector import fetch_cpu_utilization

cpu = fetch_cpu_utilization("0000000")

print("CPU:", cpu)
