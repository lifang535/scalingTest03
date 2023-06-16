all_workers = 60
# split = 500
split = 320
over_provisioning = 1.2
# ssd_mobilenet
load_time = 2.9  # 冷启动时间
batch_sizes = [1, 2, 4, 8, 16, 32]
durations = [0.069, 0.117, 0.209, 0.396, 0.771, 1.544]
SLO = 0.500  # 500 ms

# 20400:20499

client_address = "localhost:20400"
frontend_address = "localhost:20401"
worker_addresses = [f"localhost:{port}" for port in range(20402, 20402 + all_workers)]
#worker_addresses = [f"localhost:2040{i}" for i in range(2, all_workers + 2)]
"""
client_address = "localhost:21300"
frontend_address = "localhost:21301"
worker_addresses = [f"localhost:2130{i}" for i in range(2, all_workers + 2)]
"""

# kill 20400:20499, 21300:21399
