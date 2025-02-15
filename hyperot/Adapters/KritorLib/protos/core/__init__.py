# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: core/core.proto
# plugin: python-betterproto
# This file has been @generated

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional

import grpclib
import betterproto
from betterproto.grpc.grpclib_server import ServiceBase

if TYPE_CHECKING:
    import grpclib.server
    from grpclib.metadata import Deadline
    from betterproto.grpc.grpclib_client import MetadataLike


@dataclass(eq=False, repr=False)
class GetVersionRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class GetVersionResponse(betterproto.Message):
    version: str = betterproto.string_field(1)
    app_name: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class DownloadFileRequest(betterproto.Message):
    url: Optional[str] = betterproto.string_field(1, optional=True, group="_url")
    base64: Optional[str] = betterproto.string_field(2, optional=True, group="_base64")
    root_path: Optional[str] = betterproto.string_field(3, optional=True, group="_root_path")
    file_name: Optional[str] = betterproto.string_field(4, optional=True, group="_file_name")
    thread_cnt: Optional[int] = betterproto.uint32_field(5, optional=True, group="_thread_cnt")
    headers: Optional[str] = betterproto.string_field(6, optional=True, group="_headers")


@dataclass(eq=False, repr=False)
class DownloadFileResponse(betterproto.Message):
    file_absolute_path: str = betterproto.string_field(1)
    file_md5: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class GetCurrentAccountRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class GetCurrentAccountResponse(betterproto.Message):
    account_uid: str = betterproto.string_field(1)
    account_uin: int = betterproto.uint64_field(2)
    account_name: str = betterproto.string_field(3)


@dataclass(eq=False, repr=False)
class SwitchAccountRequest(betterproto.Message):
    account_uid: str = betterproto.string_field(1, group="account")
    account_uin: int = betterproto.uint64_field(2, group="account")
    super_ticket: str = betterproto.string_field(3)


@dataclass(eq=False, repr=False)
class SwitchAccountResponse(betterproto.Message):
    pass


class CoreServiceStub(betterproto.ServiceStub):
    async def get_version(
        self,
        get_version_request: "GetVersionRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetVersionResponse":
        return await self._unary_unary(
            "/kritor.core.CoreService/GetVersion",
            get_version_request,
            GetVersionResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def download_file(
        self,
        download_file_request: "DownloadFileRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "DownloadFileResponse":
        return await self._unary_unary(
            "/kritor.core.CoreService/DownloadFile",
            download_file_request,
            DownloadFileResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_current_account(
        self,
        get_current_account_request: "GetCurrentAccountRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetCurrentAccountResponse":
        return await self._unary_unary(
            "/kritor.core.CoreService/GetCurrentAccount",
            get_current_account_request,
            GetCurrentAccountResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def switch_account(
        self,
        switch_account_request: "SwitchAccountRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SwitchAccountResponse":
        return await self._unary_unary(
            "/kritor.core.CoreService/SwitchAccount",
            switch_account_request,
            SwitchAccountResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )


class CoreServiceBase(ServiceBase):

    async def get_version(self, get_version_request: "GetVersionRequest") -> "GetVersionResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def download_file(self, download_file_request: "DownloadFileRequest") -> "DownloadFileResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_current_account(
        self, get_current_account_request: "GetCurrentAccountRequest"
    ) -> "GetCurrentAccountResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def switch_account(self, switch_account_request: "SwitchAccountRequest") -> "SwitchAccountResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def __rpc_get_version(self, stream: "grpclib.server.Stream[GetVersionRequest, GetVersionResponse]") -> None:
        request = await stream.recv_message()
        response = await self.get_version(request)
        await stream.send_message(response)

    async def __rpc_download_file(
        self, stream: "grpclib.server.Stream[DownloadFileRequest, DownloadFileResponse]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.download_file(request)
        await stream.send_message(response)

    async def __rpc_get_current_account(
        self,
        stream: "grpclib.server.Stream[GetCurrentAccountRequest, GetCurrentAccountResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_current_account(request)
        await stream.send_message(response)

    async def __rpc_switch_account(
        self,
        stream: "grpclib.server.Stream[SwitchAccountRequest, SwitchAccountResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.switch_account(request)
        await stream.send_message(response)

    def __mapping__(self) -> Dict[str, grpclib.const.Handler]:
        return {
            "/kritor.core.CoreService/GetVersion": grpclib.const.Handler(
                self.__rpc_get_version,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetVersionRequest,
                GetVersionResponse,
            ),
            "/kritor.core.CoreService/DownloadFile": grpclib.const.Handler(
                self.__rpc_download_file,
                grpclib.const.Cardinality.UNARY_UNARY,
                DownloadFileRequest,
                DownloadFileResponse,
            ),
            "/kritor.core.CoreService/GetCurrentAccount": grpclib.const.Handler(
                self.__rpc_get_current_account,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetCurrentAccountRequest,
                GetCurrentAccountResponse,
            ),
            "/kritor.core.CoreService/SwitchAccount": grpclib.const.Handler(
                self.__rpc_switch_account,
                grpclib.const.Cardinality.UNARY_UNARY,
                SwitchAccountRequest,
                SwitchAccountResponse,
            ),
        }
