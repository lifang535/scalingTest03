import grpc
import time
from math import ceil
import logging

import threading
import multiprocessing
from concurrent import futures

import _utils
import simulation_pb2, simulation_pb2_grpc
from _config import client_address, frontend_address, worker_addresses, batch_sizes, durations

# 配置 logging
logger_worker = logging.getLogger('logger_worker')
logger_worker.setLevel(logging.INFO)
fh = logging.FileHandler('logs/worker.log', mode='w')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger_worker.addHandler(fh)

#logging.getLogger('logger_worker').disabled = False

"""
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='logs/worker.log',
                    filemode='w')
"""

class Worker(simulation_pb2_grpc.InferenceServicer):
    # 初始化 Worker
    def __init__(self, name, server, worker_address, status=True, is_working=False, is_ready=False, duration=0.209):
        # 用 SendWorkerStatus 向 Frontend 发送请求
        self.frontend_address = frontend_address
        self.channel = grpc.insecure_channel(frontend_address)
        self.stub = simulation_pb2_grpc.InferenceStub(self.channel)
        
        self.name = name  # worker 的名字
        self.wid = int(name.split("-")[1])  # worker 的 id
        self.server = server  # 用于停止 Worker
        self.worker_address = worker_address  # worker 的地址
        self.status = status  # 控制 Worker 服务停止
        self.is_working = is_working  # 控制 Worker 的状态
        self.duration = duration  # 每个 batch 的处理时间
        self.queue = []  # batches of processing / ed
        self.start_adj = time.time()
        self.end_adj = time.time()

        #self.adj_worker_times = []
        self.is_ready = is_ready  # 冷启动操作

        self.lock = threading.Lock()  # 用于线程同步
        
        """
        ssd_mobilenet
        1 - 69 ms
        2 - 117
        4 - 209
        8 - 396
        16 - 771
        32 - 1544
        """
        self.batch_sizes = batch_sizes
        self.durations = durations
    
    # 实现 ProcessBatch RPC 方法
    def ProcessBatch(self, batch, context):
        try:
            # 第一次调用 ProcessBatch 时打开 monitor 线程
            if len(self.queue) == 0:
                worker_monitor = threading.Thread(target=self.monitor)
                worker_monitor.start()

            self.is_working = True  # rpc 传送相关信息
            status = simulation_pb2.Request(message_type=3, id=self.wid, worker_status=self.is_working)
            self.stub.SendRequest(status)

            for batch_size in self.batch_sizes:
                if len(batch.requests) <= batch_size:
                    self.duration = self.durations[self.batch_sizes.index(batch_size)]
                    break

            #time.sleep(max(self.duration - (self.end_adj - self.start_adj), 0))
            time.sleep(self.duration)

            self.start_adj = time.time()

            self.queue.append(batch.requests)
            end_time = int(time.time() * 1e6)
            end_times = []
            for _ in range(len(batch.requests)):
                end_times.append(end_time)
            latencies = [end_time - request.data_time for request in batch.requests]
            # self.queue.pop(0)
            with self.lock:
                print(f"[{self.name}] latency: {', '.join([f'{l / 1e3:.1f}' for l in latencies])} | Qsize={len(self.queue)}")
                #logging.info(f"[{self.name}] latency: {', '.join([f'{l / 1e3:.1f}' for l in latencies])} | Qsize={len(self.queue)}")
                logger_worker.info(f"[{self.name}] latency: {', '.join([f'{l / 1e3:.1f}' for l in latencies])} | Qsize={len(self.queue)}")
            
            self.is_working = False
            status = simulation_pb2.Request(message_type=3, id=self.wid, worker_status=self.is_working)
            self.stub.SendRequest(status)

            self.end_adj = time.time()

            adj_worker_times = []
            for _ in range(len(batch.requests)):
                adj_worker_times.append(int((self.end_adj - self.start_adj) * 1e6))

            response = simulation_pb2.BatchResponse(end_times=end_times, adj_worker_times=adj_worker_times)
            return response  # 返回一组结束时间和需要后处理的时间
        
        except:
            print(f"[{self.name}] error in ProcessBatch")
            logger_worker.info(f"[{self.name}] error in ProcessBatch, the first request in batch is: {format(batch[0].id)}")
            return
        
    def monitor(self):
        while True:
            if not self.status:
                self.server.stop(0)
                #grpc.Server.stop()
                print(f"[{self.name}] server is stopped")
                #logging.info(f"[{self.name}] server is stopped")
                logger_worker.info(f"[{self.name}] server is stopped")
                break
            time.sleep(0.01)
    
    def SendRequest(self, request, context):
        # 第一次调用 ProcessBatch 时打开 monitor 线程
        if len(self.queue) == 0:
            worker_monitor = threading.Thread(target=self.monitor)
            worker_monitor.start()
            
        if request.message_type == 7:
            #with threading.Lock():
            #    print(f"[{self.name}] server is stopped")
            self.status = False
        return simulation_pb2.Response()

worker_servers = []

def start_worker_servers(worker_addresses, is_end):
    #worker_servers = []
    for i, worker_address in enumerate(worker_addresses):
        worker_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        #worker = Worker(f"Worker-{i+1}", worker_server)
        #simulation_pb2_grpc.add_InferenceServicer_to_server(worker, worker_server)
        simulation_pb2_grpc.add_InferenceServicer_to_server(Worker(f"Worker-{i+1}", worker_server, worker_addresses[i]), worker_server)

        worker_server.add_insecure_port(worker_address)
        worker_server.start()

        print(f"Worker-{i+1} server started on {worker_address}")
        #logging.info(f"Worker-{i+1} server started on {worker_address}")
        logger_worker.info(f"Worker-{i+1} server started on {worker_address}")
        worker_servers.append(worker_server)
    """
    while True:
        time.sleep(0.01)
        if is_end.value:
            for worker_server in worker_servers:
                worker_server.stop(0)
            break
    """
    for worker_server in worker_servers:
        worker_server.wait_for_termination()
    

if __name__ == "__main__":
    is_end = multiprocessing.Value("i", False)
    multiprocessing.Process(target=start_worker_servers, args=(worker_addresses, is_end,)).start()

