# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: reverse/reverse.proto
# plugin: python-betterproto
# This file has been @generated

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Union, Iterable, Optional, AsyncIterable, AsyncIterator

import grpclib
import betterproto
from betterproto.grpc.grpclib_server import ServiceBase

from .. import common as _common__

if TYPE_CHECKING:
    import grpclib.server
    from grpclib.metadata import Deadline
    from betterproto.grpc.grpclib_client import MetadataLike


class ReverseServiceStub(betterproto.ServiceStub):
    async def reverse_stream(
        self,
        common_response_iterator: Union[AsyncIterable["_common__.Response"], Iterable["_common__.Response"]],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> AsyncIterator["_common__.Request"]:
        async for response in self._stream_stream(
            "/kritor.reverse.ReverseService/ReverseStream",
            common_response_iterator,
            _common__.Response,
            _common__.Request,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        ):
            yield response


class ReverseServiceBase(ServiceBase):

    async def reverse_stream(
        self, common_response_iterator: AsyncIterator["_common__.Response"]
    ) -> AsyncIterator["_common__.Request"]:
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)
        yield _common__.Request()

    async def __rpc_reverse_stream(
        self, stream: "grpclib.server.Stream[_common__.Response, _common__.Request]"
    ) -> None:
        request = stream.__aiter__()
        await self._call_rpc_handler_server_stream(
            self.reverse_stream,
            stream,
            request,
        )

    def __mapping__(self) -> Dict[str, grpclib.const.Handler]:
        return {
            "/kritor.reverse.ReverseService/ReverseStream": grpclib.const.Handler(
                self.__rpc_reverse_stream,
                grpclib.const.Cardinality.STREAM_STREAM,
                _common__.Response,
                _common__.Request,
            ),
        }