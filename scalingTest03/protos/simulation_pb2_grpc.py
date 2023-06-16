# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

import simulation_pb2 as simulation__pb2


class InferenceStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.SendRequest = channel.unary_unary(
                '/simulation.Inference/SendRequest',
                request_serializer=simulation__pb2.Request.SerializeToString,
                response_deserializer=simulation__pb2.Response.FromString,
                )
        self.ProcessBatch = channel.unary_unary(
                '/simulation.Inference/ProcessBatch',
                request_serializer=simulation__pb2.Batch.SerializeToString,
                response_deserializer=simulation__pb2.BatchResponse.FromString,
                )


class InferenceServicer(object):
    """Missing associated documentation comment in .proto file."""

    def SendRequest(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ProcessBatch(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_InferenceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'SendRequest': grpc.unary_unary_rpc_method_handler(
                    servicer.SendRequest,
                    request_deserializer=simulation__pb2.Request.FromString,
                    response_serializer=simulation__pb2.Response.SerializeToString,
            ),
            'ProcessBatch': grpc.unary_unary_rpc_method_handler(
                    servicer.ProcessBatch,
                    request_deserializer=simulation__pb2.Batch.FromString,
                    response_serializer=simulation__pb2.BatchResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'simulation.Inference', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class Inference(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def SendRequest(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/simulation.Inference/SendRequest',
            simulation__pb2.Request.SerializeToString,
            simulation__pb2.Response.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def ProcessBatch(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/simulation.Inference/ProcessBatch',
            simulation__pb2.Batch.SerializeToString,
            simulation__pb2.BatchResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)