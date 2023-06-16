import grpc
import time
from math import ceil
import logging

import threading
import multiprocessing
from concurrent import futures

import _utils
import simulation_pb2, simulation_pb2_grpc
from _config import client_address, frontend_address, worker_addresses, all_workers, over_provisioning, load_time, batch_sizes, durations, SLO
from worker import Worker

# 配置 logging
logger_frontend = logging.getLogger('logger_frontend')
logger_frontend.setLevel(logging.INFO)
fh = logging.FileHandler('logs/frontend.log', mode='w')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger_frontend.addHandler(fh)

logging.getLogger('logger_worker').disabled = True

class Frontend(simulation_pb2_grpc.InferenceServicer):
    # 初始化 Frontend
    def __init__(self, workers, server, duration=0.209, batch_size=4, num_workers=0, load_time=load_time, status=True):
        # 用 ProcessBatch 向 Workers 发送请求
        self.worker_addresses = worker_addresses
        self.channels = [grpc.insecure_channel(address) for address in self.worker_addresses] 
        self.stubs = [simulation_pb2_grpc.InferenceStub(channel) for channel in self.channels]

        # 用 SendRequest 向 Client 发送请求
        self.client_address = client_address
        self.channel = grpc.insecure_channel(client_address)
        self.stub = simulation_pb2_grpc.InferenceStub(self.channel)

        self.workers = workers  # 存储 worker 的信息
        #self.worker_is_working = workers  # 存储 worker 的状态
        self.server = server  # 用于停止 Frontend
        self.duration = duration  # 每个 batch 的处理时间
        self.batch_size = batch_size  # 每个 batch 中包含的 requests 的数量
        self.num_workers = num_workers  # 工作的 worker 数量
        self.status = status  # 控制两个线程同时停止

        self.queue = []  # 所有的 requests
        self.times = []  # 用于测量 rate
        self.threadings = []   # 用于存储线程
        
        self.rate = 0  # 用于展示所测量 rate

        self.lock = threading.Lock()  # 用于线程同步

        self.load_time = load_time  # 用于冷启动 worker

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
        self.index = 2
        self.SLO = SLO
        """
        latency = duration + (batch_size - 1) * duration / rate <= SLO
        """

    def SendRequest(self, request, context):
        if request.message_type == 1:
            self.times.append(time.time())

            # 第一次调用 SendRequest 时打开 monitor 线程，show_parameters 线程， monitor_queue 线程，以及 monitor_batch_size 线程
            if self.num_workers == 0:
                frontend_monitor = threading.Thread(target=self.monitor)
                frontend_monitor.start()
                self.num_workers += 30
                for i in range(30):
                    self.workers[i].is_ready = True

                frontend_show_parameters = threading.Thread(target=self.show_parameters)
                frontend_show_parameters.start()
                
                frontend_monitor_queue = threading.Thread(target=self.monitor_queue)
                frontend_monitor_queue.start()

                frontend_monitor_batch_size = threading.Thread(target=self.monitor_batch_size)
                frontend_monitor_batch_size.start()

            self.queue.append(request)
            return simulation_pb2.Response()
        
        elif request.message_type == 3:
            self.workers[request.id - 1].is_working = request.worker_status    
            #self.worker_is_working[request.id - 1] = request.worker_status
            return simulation_pb2.Response()
        elif request.message_type == 6:
            with self.lock:
                print("[Frontend] server is stopped")
                logger_frontend.info("[Frontend] server is stopped")
            self.status = False
            return simulation_pb2.Response()

    def monitor_queue(self):
        with self.lock:
            print("[Frontend] monitor_queue is working")
            logger_frontend.info("[Frontend] monitor_queue is working")
        timer_waiting = time.time()
        while True:
            if not self.status:
                break
            now = time.time()
            last_batch_size = self.batch_size  # 防止在计算过程中 self.batch_size 发生变化
            if len(self.queue) >= last_batch_size:
                batch = self.queue[:last_batch_size]
                self.queue = self.queue[last_batch_size:]

                send_batches = threading.Thread(target=self.send_batches, args=(batch,))
                send_batches.start()

                timer_waiting = now

                #self.send_batches(batch)
            if now - timer_waiting >= self.SLO - self.duration:  # 如果等待时间超过 SLO - duration，就发送请求
                timer_waiting = now
                if len(self.queue) > 0:
                    logger_frontend.warning("[Frontend] timeout, batch_size = {}".format(len(self.queue)))
                    batch = self.queue
                    self.queue = []

                    send_batches = threading.Thread(target=self.send_batches, args=(batch,))
                    send_batches.start()
                    #self.send_batches(batch)
                #print("[Frontend] queue size: {}".format(len(self.queue)))
                    

            time.sleep(0.01)

    def monitor_batch_size(self):
        with self.lock:
            print("[Frontend] monitor_batch_size is working")
            logger_frontend.info("[Frontend] monitor_batch_size is working")
        while True:
            if not self.status:
                break
            for i in range(len(self.batch_sizes)):
                if self.rate != 0 and self.durations[i] + (self.batch_sizes[i] - 1) * self.durations[i] / self.rate <= self.SLO:
                    self.index = i
            if self.batch_size != self.batch_sizes[self.index]:
                self.batch_size = self.batch_sizes[self.index]
                self.duration = self.durations[self.index]
                print("[Frontend] batch_size is changed to {}".format(self.batch_size))
                logger_frontend.info("[Frontend] batch_size is changed to {}".format(self.batch_size))
            time.sleep(0.01)
    

    def send_batches(self, batch):
        try:
            i = self.select_worker()
            #print("[Frontend] send batch to worker {}".format(i))
            if i == -1:  # 没有可用的 worker
                print("[Frontend] no available worker")
                logger_frontend.warning("[Frontend] no available worker, drop the batch, and the first request in batch is: {}".format(batch[0].id))
                logger_frontend.warning("[Frontend] the measured rate is: {}".format(self.rate))
                logger_frontend.warning("[Frontend] the num_workers is: {}".format(self.num_workers))
                time.sleep(self.duration)
                end_times = [batch[i].data_time for i in range(len(batch))]
                adj_worker_times = [0] * len(batch)
                for end_time, adj_worker_time in zip(end_times, adj_worker_times):
                    request = simulation_pb2.Request(message_type=4, data_time=end_time, adj_worker_time=adj_worker_time)
                    response = self.stub.SendRequest(request)
                return
                
            requests = simulation_pb2.Batch(requests=batch)
            batch_response = self.stubs[i].ProcessBatch(requests)
            end_times = batch_response.end_times
            adj_worker_times = batch_response.adj_worker_times
        except:
            print("[Frontend] error in send_batches")
            logger_frontend.error("[Frontend] error in send_batches, the first request in batch is: {}".format(batch[0].id))
            return

        #batch_request = simulation_pb2.Request(message_type=2, requests=batch)
        #batch_response = self.stubs[i].SendRequest(batch_request)

        for end_time, adj_worker_time in zip(end_times, adj_worker_times):
            request = simulation_pb2.Request(message_type=4, data_time=end_time, adj_worker_time=adj_worker_time)
            response = self.stub.SendRequest(request)
            #self.stub.SendEndTime(simulation_pb2.EndTime(time=end_time, adj_worker_time=adj_worker_time))

        #return batch_response.end_times

    # Frontend 的监测器 rate and stop_flag
    def monitor(self):
        with self.lock:
            print("[Frontend] monitor is working")
            logger_frontend.info("[Frontend] monitor is working")
        time.sleep(0.1)
        rates = []
        timer_show_num_workers = time.time()
        while True:
            if not self.status:
                self.num_workers = 0
                time.sleep(0.1)
                
                for stub in self.stubs:
                    # 发送结束信号 -1
                    request = simulation_pb2.Request(message_type=7)
                    response = stub.SendRequest(request)
                    #stub.SendRequest(simulation_pb2.Request(start_time=-1))

                self.server.stop(0)
                with self.lock:
                    print("[Frontend] monitor is stopped")
                    logger_frontend.info("[Frontend] monitor is stopped")
                break
            last_batch_size = self.batch_size  # 防止在计算过程中 self.batch_size 发生变化
            if len(self.times) >= last_batch_size:
                rate = last_batch_size / (self.times[last_batch_size - 1] - self.times[0])
                rates.append(rate)
                self.times = self.times[last_batch_size:]
            if len(rates) >= 1:
                #self.rate = ceil(sum(rates) / len(rates))
                """
                self.rate = 0
                for i in range(10):
                    self.rate += ceil(rates[i] * (i + 1) / 55)
                """
                #self.rate = ceil(sum(ceil(rates[i] * (i + 1) / (sum(j for j in range(1, len(rates))))) for i in range(len(rates) - 1)) * 1 / 3 + rates[len(rates) - 1] * 2 / 3)
                self.rate = ceil(sum(ceil(rates[i] * (i + 1) / (sum(j for j in range(1, len(rates))))) for i in range(len(rates) - 1)) * 1 / 3 + rates[len(rates) - 1] * 2 / 3)
                last_num_workers = self.num_workers  # 保存上一次的 worker 数量
                #self.num_workers = max(ceil(self.duration * (sum(rates) / len(rates)) / self.batch_size), 1)  # 调整工作的 worker 数量
                self.num_workers = max(ceil(self.duration * self.rate / self.batch_size * over_provisioning + 5), 1)  # 调整工作的 worker 数量                
                if self.num_workers > last_num_workers:  # 冷启动新的 worker
                    #time.sleep(1)
                    cold_start_worker = threading.Thread(target=self.cold_start_worker, args=(last_num_workers,))
                    cold_start_worker.start()
                elif self.num_workers < last_num_workers:  # 关闭多余的 worker
                    for i in range(self.num_workers, last_num_workers):
                        self.workers[i].is_ready = False
                #rates = []
                if len(rates) >= 10:  # 滑动窗口大小为 10
                    rates = rates[1:]
            now = time.time()
            if now - timer_show_num_workers >= 0.1:
                timer_show_num_workers = time.time()
                request = simulation_pb2.Request(message_type=5, num_workers=ceil(self.num_workers))
                response = self.stub.SendRequest(request)
                #self.stub.SendRequest(simulation_pb2.Request(id=-2, num_workers=self.num_workers + 1))
                #print("[Frontend] sent the number of workers:", self.num_workers, ", to the client")
            time.sleep(0.01)

    # 冷启动 worker
    def cold_start_worker(self, last_num_workers):
        time.sleep(self.load_time)
        if not self.status:
            return
        for i in range(last_num_workers, self.num_workers):
            self.workers[i].is_ready = True

    def show_parameters(self):
        while True:
            if not self.status:
                break
            with self.lock:
                print(f"[Frontend] the measured rate = {self.rate}")
                print(f"[Frontend] the number of workers = {min(ceil(self.num_workers), len(self.workers))}")
                logger_frontend.info(f"[Frontend] the measured rate = {self.rate}")
                logger_frontend.info(f"[Frontend] the number of workers = {min(ceil(self.num_workers), len(self.workers))}")
            time.sleep(1)

    # 选择 worker
    def select_worker(self):  # 问题：num_workers 向上调整过大
        for i in range(min(ceil(self.num_workers), len(self.workers))):
        #for i in range(min(ceil(self.num_workers * over_provisioning), len(self.worker_is_working))):
        # for i in range(len(self.workers)):
            if not self.workers[i].is_working and self.workers[i].is_ready:
            #if not self.worker_is_working[i]:
                # return self.workers[i]
                return i
        return -1

frontend_server = grpc.server(futures.ThreadPoolExecutor(max_workers=all_workers + 2))

def start_frontend_server(frontend_address, is_end):
    #frontend_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    logging.getLogger('logger_worker').disabled = True
    workers = [Worker(f"Worker-{i+1}", grpc.server(futures.ThreadPoolExecutor(max_workers=10)), worker_addresses[i]) for i in range(all_workers)]
    #worker_is_workings = [False for i in range(all_workers)]
    #frontend = Frontend(workers, frontend_server)
    frontend = Frontend(workers, frontend_server)
    for worker in workers:
    #for worker_is_working in worker_is_workings:
        simulation_pb2_grpc.add_InferenceServicer_to_server(frontend, frontend_server)
    frontend_server.add_insecure_port(frontend_address)
    frontend_server.start()
    """
    while True:
        time.sleep(0.01)
        if is_end.value:
            frontend_server.stop(0)
            break
    """
    frontend_server.wait_for_termination()
    

if __name__ == "__main__":
    is_end = multiprocessing.Value("i", 0)
    multiprocessing.Process(target=start_frontend_server, args=(frontend_address, is_end,)).start()
