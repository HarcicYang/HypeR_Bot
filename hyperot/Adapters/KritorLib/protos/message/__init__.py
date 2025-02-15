# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: message/message.proto
# plugin: python-betterproto
# This file has been @generated

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

import grpclib
import betterproto
from betterproto.grpc.grpclib_server import ServiceBase

from .. import common as _common__

if TYPE_CHECKING:
    import grpclib.server
    from grpclib.metadata import Deadline
    from betterproto.grpc.grpclib_client import MetadataLike


@dataclass(eq=False, repr=False)
class SendMessageRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    elements: List["_common__.Element"] = betterproto.message_field(2)
    retry_count: Optional[int] = betterproto.uint32_field(3, optional=True, group="_retry_count")
    message_id: Optional[str] = betterproto.string_field(4, optional=True, group="_message_id")
    """passive_id"""

    notice_id: Optional[str] = betterproto.string_field(5, optional=True, group="_notice_id")
    request_id: Optional[str] = betterproto.string_field(6, optional=True, group="_request_id")


@dataclass(eq=False, repr=False)
class SendMessageResponse(betterproto.Message):
    message_id: str = betterproto.string_field(1)
    message_time: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class SendMessageByResIdRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    res_id: str = betterproto.string_field(2)
    retry_count: Optional[int] = betterproto.uint32_field(3, optional=True, group="_retry_count")


@dataclass(eq=False, repr=False)
class SendMessageByResIdResponse(betterproto.Message):
    message_id: str = betterproto.string_field(1)
    message_time: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class SetMessageReadRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class SetMessageReadResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class RecallMessageRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    message_id: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class RecallMessageResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class ReactMessageWithEmojiRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    message_id: str = betterproto.string_field(2)
    face_id: int = betterproto.uint32_field(3)
    is_set: bool = betterproto.bool_field(4)


@dataclass(eq=False, repr=False)
class ReactMessageWithEmojiResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class GetMessageRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    message_id: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class GetMessageResponse(betterproto.Message):
    message: "_common__.PushMessageBody" = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetMessageBySeqRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    message_seq: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class GetMessageBySeqResponse(betterproto.Message):
    message: "_common__.PushMessageBody" = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetHistoryMessageRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    start_message_id: Optional[str] = betterproto.string_field(2, optional=True, group="_start_message_id")
    count: Optional[int] = betterproto.uint32_field(3, optional=True, group="_count")


@dataclass(eq=False, repr=False)
class GetHistoryMessageResponse(betterproto.Message):
    messages: List["_common__.PushMessageBody"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetHistoryMessageBySeqRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    start_message_seq: Optional[int] = betterproto.uint64_field(2, optional=True, group="_start_message_seq")
    count: Optional[int] = betterproto.uint32_field(3, optional=True, group="_count")


@dataclass(eq=False, repr=False)
class GetHistoryMessageBySeqResponse(betterproto.Message):
    messages: List["_common__.PushMessageBody"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class UploadForwardMessageRequest(betterproto.Message):
    contact: "_common__.Contact" = betterproto.message_field(1)
    messages: List["_common__.ForwardMessageBody"] = betterproto.message_field(2)
    retry_count: Optional[int] = betterproto.uint32_field(3, optional=True, group="_retry_count")


@dataclass(eq=False, repr=False)
class UploadForwardMessageResponse(betterproto.Message):
    res_id: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class DownloadForwardMessageRequest(betterproto.Message):
    res_id: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class DownloadForwardMessageResponse(betterproto.Message):
    messages: List["_common__.PushMessageBody"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetEssenceMessageListRequest(betterproto.Message):
    group_id: int = betterproto.uint64_field(1)
    page: int = betterproto.uint32_field(2)
    page_size: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class GetEssenceMessageListResponse(betterproto.Message):
    messages: List["_common__.EssenceMessageBody"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class SetEssenceMessageRequest(betterproto.Message):
    group_id: int = betterproto.uint64_field(1)
    message_id: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class SetEssenceMessageResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class DeleteEssenceMessageRequest(betterproto.Message):
    group_id: int = betterproto.uint64_field(1)
    message_id: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class DeleteEssenceMessageResponse(betterproto.Message):
    pass


class MessageServiceStub(betterproto.ServiceStub):
    async def send_message(
        self,
        send_message_request: "SendMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SendMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/SendMessage",
            send_message_request,
            SendMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def send_message_by_res_id(
        self,
        send_message_by_res_id_request: "SendMessageByResIdRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SendMessageByResIdResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/SendMessageByResId",
            send_message_by_res_id_request,
            SendMessageByResIdResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def set_message_readed(
        self,
        set_message_read_request: "SetMessageReadRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SetMessageReadResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/SetMessageReaded",
            set_message_read_request,
            SetMessageReadResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def recall_message(
        self,
        recall_message_request: "RecallMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "RecallMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/RecallMessage",
            recall_message_request,
            RecallMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def react_message_with_emoji(
        self,
        react_message_with_emoji_request: "ReactMessageWithEmojiRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "ReactMessageWithEmojiResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/ReactMessageWithEmoji",
            react_message_with_emoji_request,
            ReactMessageWithEmojiResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_message(
        self,
        get_message_request: "GetMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/GetMessage",
            get_message_request,
            GetMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_message_by_seq(
        self,
        get_message_by_seq_request: "GetMessageBySeqRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetMessageBySeqResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/GetMessageBySeq",
            get_message_by_seq_request,
            GetMessageBySeqResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_history_message(
        self,
        get_history_message_request: "GetHistoryMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetHistoryMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/GetHistoryMessage",
            get_history_message_request,
            GetHistoryMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_history_message_by_seq(
        self,
        get_history_message_by_seq_request: "GetHistoryMessageBySeqRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetHistoryMessageBySeqResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/GetHistoryMessageBySeq",
            get_history_message_by_seq_request,
            GetHistoryMessageBySeqResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def upload_forward_message(
        self,
        upload_forward_message_request: "UploadForwardMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "UploadForwardMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/UploadForwardMessage",
            upload_forward_message_request,
            UploadForwardMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def download_forward_message(
        self,
        download_forward_message_request: "DownloadForwardMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "DownloadForwardMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/DownloadForwardMessage",
            download_forward_message_request,
            DownloadForwardMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_essence_message_list(
        self,
        get_essence_message_list_request: "GetEssenceMessageListRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetEssenceMessageListResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/GetEssenceMessageList",
            get_essence_message_list_request,
            GetEssenceMessageListResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def set_essence_message(
        self,
        set_essence_message_request: "SetEssenceMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SetEssenceMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/SetEssenceMessage",
            set_essence_message_request,
            SetEssenceMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def delete_essence_message(
        self,
        delete_essence_message_request: "DeleteEssenceMessageRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "DeleteEssenceMessageResponse":
        return await self._unary_unary(
            "/kritor.message.MessageService/DeleteEssenceMessage",
            delete_essence_message_request,
            DeleteEssenceMessageResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )


class MessageServiceBase(ServiceBase):

    async def send_message(self, send_message_request: "SendMessageRequest") -> "SendMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def send_message_by_res_id(
        self, send_message_by_res_id_request: "SendMessageByResIdRequest"
    ) -> "SendMessageByResIdResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def set_message_readed(self, set_message_read_request: "SetMessageReadRequest") -> "SetMessageReadResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def recall_message(self, recall_message_request: "RecallMessageRequest") -> "RecallMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def react_message_with_emoji(
        self, react_message_with_emoji_request: "ReactMessageWithEmojiRequest"
    ) -> "ReactMessageWithEmojiResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_message(self, get_message_request: "GetMessageRequest") -> "GetMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_message_by_seq(
        self, get_message_by_seq_request: "GetMessageBySeqRequest"
    ) -> "GetMessageBySeqResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_history_message(
        self, get_history_message_request: "GetHistoryMessageRequest"
    ) -> "GetHistoryMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_history_message_by_seq(
        self, get_history_message_by_seq_request: "GetHistoryMessageBySeqRequest"
    ) -> "GetHistoryMessageBySeqResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def upload_forward_message(
        self, upload_forward_message_request: "UploadForwardMessageRequest"
    ) -> "UploadForwardMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def download_forward_message(
        self, download_forward_message_request: "DownloadForwardMessageRequest"
    ) -> "DownloadForwardMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_essence_message_list(
        self, get_essence_message_list_request: "GetEssenceMessageListRequest"
    ) -> "GetEssenceMessageListResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def set_essence_message(
        self, set_essence_message_request: "SetEssenceMessageRequest"
    ) -> "SetEssenceMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def delete_essence_message(
        self, delete_essence_message_request: "DeleteEssenceMessageRequest"
    ) -> "DeleteEssenceMessageResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def __rpc_send_message(
        self, stream: "grpclib.server.Stream[SendMessageRequest, SendMessageResponse]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.send_message(request)
        await stream.send_message(response)

    async def __rpc_send_message_by_res_id(
        self,
        stream: "grpclib.server.Stream[SendMessageByResIdRequest, SendMessageByResIdResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.send_message_by_res_id(request)
        await stream.send_message(response)

    async def __rpc_set_message_readed(
        self,
        stream: "grpclib.server.Stream[SetMessageReadRequest, SetMessageReadResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.set_message_readed(request)
        await stream.send_message(response)

    async def __rpc_recall_message(
        self,
        stream: "grpclib.server.Stream[RecallMessageRequest, RecallMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.recall_message(request)
        await stream.send_message(response)

    async def __rpc_react_message_with_emoji(
        self,
        stream: "grpclib.server.Stream[ReactMessageWithEmojiRequest, ReactMessageWithEmojiResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.react_message_with_emoji(request)
        await stream.send_message(response)

    async def __rpc_get_message(self, stream: "grpclib.server.Stream[GetMessageRequest, GetMessageResponse]") -> None:
        request = await stream.recv_message()
        response = await self.get_message(request)
        await stream.send_message(response)

    async def __rpc_get_message_by_seq(
        self,
        stream: "grpclib.server.Stream[GetMessageBySeqRequest, GetMessageBySeqResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_message_by_seq(request)
        await stream.send_message(response)

    async def __rpc_get_history_message(
        self,
        stream: "grpclib.server.Stream[GetHistoryMessageRequest, GetHistoryMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_history_message(request)
        await stream.send_message(response)

    async def __rpc_get_history_message_by_seq(
        self,
        stream: "grpclib.server.Stream[GetHistoryMessageBySeqRequest, GetHistoryMessageBySeqResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_history_message_by_seq(request)
        await stream.send_message(response)

    async def __rpc_upload_forward_message(
        self,
        stream: "grpclib.server.Stream[UploadForwardMessageRequest, UploadForwardMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.upload_forward_message(request)
        await stream.send_message(response)

    async def __rpc_download_forward_message(
        self,
        stream: "grpclib.server.Stream[DownloadForwardMessageRequest, DownloadForwardMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.download_forward_message(request)
        await stream.send_message(response)

    async def __rpc_get_essence_message_list(
        self,
        stream: "grpclib.server.Stream[GetEssenceMessageListRequest, GetEssenceMessageListResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_essence_message_list(request)
        await stream.send_message(response)

    async def __rpc_set_essence_message(
        self,
        stream: "grpclib.server.Stream[SetEssenceMessageRequest, SetEssenceMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.set_essence_message(request)
        await stream.send_message(response)

    async def __rpc_delete_essence_message(
        self,
        stream: "grpclib.server.Stream[DeleteEssenceMessageRequest, DeleteEssenceMessageResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.delete_essence_message(request)
        await stream.send_message(response)

    def __mapping__(self) -> Dict[str, grpclib.const.Handler]:
        return {
            "/kritor.message.MessageService/SendMessage": grpclib.const.Handler(
                self.__rpc_send_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                SendMessageRequest,
                SendMessageResponse,
            ),
            "/kritor.message.MessageService/SendMessageByResId": grpclib.const.Handler(
                self.__rpc_send_message_by_res_id,
                grpclib.const.Cardinality.UNARY_UNARY,
                SendMessageByResIdRequest,
                SendMessageByResIdResponse,
            ),
            "/kritor.message.MessageService/SetMessageReaded": grpclib.const.Handler(
                self.__rpc_set_message_readed,
                grpclib.const.Cardinality.UNARY_UNARY,
                SetMessageReadRequest,
                SetMessageReadResponse,
            ),
            "/kritor.message.MessageService/RecallMessage": grpclib.const.Handler(
                self.__rpc_recall_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                RecallMessageRequest,
                RecallMessageResponse,
            ),
            "/kritor.message.MessageService/ReactMessageWithEmoji": grpclib.const.Handler(
                self.__rpc_react_message_with_emoji,
                grpclib.const.Cardinality.UNARY_UNARY,
                ReactMessageWithEmojiRequest,
                ReactMessageWithEmojiResponse,
            ),
            "/kritor.message.MessageService/GetMessage": grpclib.const.Handler(
                self.__rpc_get_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetMessageRequest,
                GetMessageResponse,
            ),
            "/kritor.message.MessageService/GetMessageBySeq": grpclib.const.Handler(
                self.__rpc_get_message_by_seq,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetMessageBySeqRequest,
                GetMessageBySeqResponse,
            ),
            "/kritor.message.MessageService/GetHistoryMessage": grpclib.const.Handler(
                self.__rpc_get_history_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetHistoryMessageRequest,
                GetHistoryMessageResponse,
            ),
            "/kritor.message.MessageService/GetHistoryMessageBySeq": grpclib.const.Handler(
                self.__rpc_get_history_message_by_seq,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetHistoryMessageBySeqRequest,
                GetHistoryMessageBySeqResponse,
            ),
            "/kritor.message.MessageService/UploadForwardMessage": grpclib.const.Handler(
                self.__rpc_upload_forward_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                UploadForwardMessageRequest,
                UploadForwardMessageResponse,
            ),
            "/kritor.message.MessageService/DownloadForwardMessage": grpclib.const.Handler(
                self.__rpc_download_forward_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                DownloadForwardMessageRequest,
                DownloadForwardMessageResponse,
            ),
            "/kritor.message.MessageService/GetEssenceMessageList": grpclib.const.Handler(
                self.__rpc_get_essence_message_list,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetEssenceMessageListRequest,
                GetEssenceMessageListResponse,
            ),
            "/kritor.message.MessageService/SetEssenceMessage": grpclib.const.Handler(
                self.__rpc_set_essence_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                SetEssenceMessageRequest,
                SetEssenceMessageResponse,
            ),
            "/kritor.message.MessageService/DeleteEssenceMessage": grpclib.const.Handler(
                self.__rpc_delete_essence_message,
                grpclib.const.Cardinality.UNARY_UNARY,
                DeleteEssenceMessageRequest,
                DeleteEssenceMessageResponse,
            ),
        }
