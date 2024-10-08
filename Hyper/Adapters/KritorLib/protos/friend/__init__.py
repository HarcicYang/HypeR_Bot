# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: friend/firend_data.proto, friend/friend.proto
# plugin: python-betterproto
# This file has been @generated

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

import grpclib
import betterproto
from betterproto.grpc.grpclib_server import ServiceBase

if TYPE_CHECKING:
    import grpclib.server
    from grpclib.metadata import Deadline
    from betterproto.grpc.grpclib_client import MetadataLike


@dataclass(eq=False, repr=False)
class FriendInfo(betterproto.Message):
    uid: str = betterproto.string_field(1)
    uin: int = betterproto.uint64_field(2)
    qid: str = betterproto.string_field(3)
    nick: str = betterproto.string_field(4)
    remark: str = betterproto.string_field(5)
    level: int = betterproto.uint32_field(6)
    age: int = betterproto.uint32_field(7)
    vote_cnt: int = betterproto.uint32_field(8)
    gender: int = betterproto.int32_field(9)
    group_id: int = betterproto.int32_field(10)
    ext: Optional["ExtInfo"] = betterproto.message_field(99, optional=True, group="_ext")


@dataclass(eq=False, repr=False)
class ProfileCard(betterproto.Message):
    uid: str = betterproto.string_field(1)
    uin: int = betterproto.uint64_field(2)
    qid: str = betterproto.string_field(3)
    nick: str = betterproto.string_field(4)
    remark: Optional[str] = betterproto.string_field(5, optional=True, group="_remark")
    level: int = betterproto.uint32_field(6)
    birthday: Optional[int] = betterproto.uint64_field(7, optional=True, group="_birthday")
    login_day: int = betterproto.uint32_field(8)
    vote_cnt: int = betterproto.uint32_field(9)
    is_school_verified: Optional[bool] = betterproto.bool_field(51, optional=True, group="_is_school_verified")
    """以下字段可以不实现"""

    ext: Optional["ExtInfo"] = betterproto.message_field(99, optional=True, group="_ext")


@dataclass(eq=False, repr=False)
class ExtInfo(betterproto.Message):
    """通用好友信息扩展字段 所有第三方协议分发扩展字段， 必须基于本字段修改， 并保存定制的副本到本仓库特定路径！！"""

    big_vip: Optional[bool] = betterproto.bool_field(1, optional=True, group="_big_vip")
    hollywood_vip: Optional[bool] = betterproto.bool_field(2, optional=True, group="_hollywood_vip")
    qq_vip: Optional[bool] = betterproto.bool_field(3, optional=True, group="_qq_vip")
    super_vip: Optional[bool] = betterproto.bool_field(4, optional=True, group="_super_vip")
    voted: Optional[bool] = betterproto.bool_field(5, optional=True, group="_voted")


@dataclass(eq=False, repr=False)
class GetFriendListRequest(betterproto.Message):
    refresh: Optional[bool] = betterproto.bool_field(1, optional=True, group="_refresh")


@dataclass(eq=False, repr=False)
class GetFriendListResponse(betterproto.Message):
    friends_info: List["FriendInfo"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetFriendProfileCardRequest(betterproto.Message):
    target_uids: List[str] = betterproto.string_field(1)
    target_uins: List[int] = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class GetFriendProfileCardResponse(betterproto.Message):
    friends_profile_card: List["ProfileCard"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetStrangerProfileCardRequest(betterproto.Message):
    target_uids: List[str] = betterproto.string_field(1)
    target_uins: List[int] = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class GetStrangerProfileCardResponse(betterproto.Message):
    strangers_profile_card: List["ProfileCard"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class SetProfileCardRequest(betterproto.Message):
    nick: Optional[str] = betterproto.string_field(1, optional=True, group="_nick")
    company: Optional[str] = betterproto.string_field(2, optional=True, group="_company")
    email: Optional[str] = betterproto.string_field(3, optional=True, group="_email")
    college: Optional[str] = betterproto.string_field(4, optional=True, group="_college")
    personal_note: Optional[str] = betterproto.string_field(5, optional=True, group="_personal_note")
    birthday: Optional[int] = betterproto.uint32_field(6, optional=True, group="_birthday")
    age: Optional[int] = betterproto.uint32_field(7, optional=True, group="_age")


@dataclass(eq=False, repr=False)
class SetProfileCardResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class IsBlackListUserRequest(betterproto.Message):
    target_uid: str = betterproto.string_field(1, group="target")
    target_uin: int = betterproto.uint64_field(2, group="target")


@dataclass(eq=False, repr=False)
class IsBlackListUserResponse(betterproto.Message):
    is_black_list_user: bool = betterproto.bool_field(1)


@dataclass(eq=False, repr=False)
class VoteUserRequest(betterproto.Message):
    target_uid: str = betterproto.string_field(1, group="target")
    target_uin: int = betterproto.uint64_field(2, group="target")
    vote_count: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class VoteUserResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class GetUidByUinRequest(betterproto.Message):
    target_uins: List[int] = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class GetUidByUinResponse(betterproto.Message):
    uid_map: Dict[int, str] = betterproto.map_field(1, betterproto.TYPE_UINT64, betterproto.TYPE_STRING)


@dataclass(eq=False, repr=False)
class GetUinByUidRequest(betterproto.Message):
    target_uids: List[str] = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class GetUinByUidResponse(betterproto.Message):
    uin_map: Dict[str, int] = betterproto.map_field(1, betterproto.TYPE_STRING, betterproto.TYPE_UINT64)


@dataclass(eq=False, repr=False)
class PrivateChatFileRequest(betterproto.Message):
    user_id: str = betterproto.string_field(1)
    file: str = betterproto.string_field(2)
    name: str = betterproto.string_field(3)


@dataclass(eq=False, repr=False)
class UploadPrivateChatFileResponse(betterproto.Message):
    file_id: str = betterproto.string_field(1)
    file_url: str = betterproto.string_field(2)
    file_name: Optional[str] = betterproto.string_field(3, optional=True, group="_file_name")
    file_size: Optional[str] = betterproto.string_field(4, optional=True, group="_file_size")
    file_bizid: Optional[str] = betterproto.string_field(5, optional=True, group="_file_bizid")
    file_sha: Optional[str] = betterproto.string_field(6, optional=True, group="_file_sha")
    file_md5: Optional[str] = betterproto.string_field(7, optional=True, group="_file_md5")


class FriendServiceStub(betterproto.ServiceStub):
    async def get_friend_list(
        self,
        get_friend_list_request: "GetFriendListRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetFriendListResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/GetFriendList",
            get_friend_list_request,
            GetFriendListResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_friend_profile_card(
        self,
        get_friend_profile_card_request: "GetFriendProfileCardRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetFriendProfileCardResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/GetFriendProfileCard",
            get_friend_profile_card_request,
            GetFriendProfileCardResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_stranger_profile_card(
        self,
        get_stranger_profile_card_request: "GetStrangerProfileCardRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetStrangerProfileCardResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/GetStrangerProfileCard",
            get_stranger_profile_card_request,
            GetStrangerProfileCardResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def set_profile_card(
        self,
        set_profile_card_request: "SetProfileCardRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "SetProfileCardResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/SetProfileCard",
            set_profile_card_request,
            SetProfileCardResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def is_black_list_user(
        self,
        is_black_list_user_request: "IsBlackListUserRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "IsBlackListUserResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/IsBlackListUser",
            is_black_list_user_request,
            IsBlackListUserResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def vote_user(
        self,
        vote_user_request: "VoteUserRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "VoteUserResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/VoteUser",
            vote_user_request,
            VoteUserResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_uid_by_uin(
        self,
        get_uid_by_uin_request: "GetUidByUinRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetUidByUinResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/GetUidByUin",
            get_uid_by_uin_request,
            GetUidByUinResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def get_uin_by_uid(
        self,
        get_uin_by_uid_request: "GetUinByUidRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "GetUinByUidResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/GetUinByUid",
            get_uin_by_uid_request,
            GetUinByUidResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )

    async def upload_private_file(
        self,
        private_chat_file_request: "PrivateChatFileRequest",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> "UploadPrivateChatFileResponse":
        return await self._unary_unary(
            "/kritor.friend.FriendService/UploadPrivateFile",
            private_chat_file_request,
            UploadPrivateChatFileResponse,
            timeout=timeout,
            deadline=deadline,
            metadata=metadata,
        )


class FriendServiceBase(ServiceBase):

    async def get_friend_list(self, get_friend_list_request: "GetFriendListRequest") -> "GetFriendListResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_friend_profile_card(
        self, get_friend_profile_card_request: "GetFriendProfileCardRequest"
    ) -> "GetFriendProfileCardResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_stranger_profile_card(
        self, get_stranger_profile_card_request: "GetStrangerProfileCardRequest"
    ) -> "GetStrangerProfileCardResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def set_profile_card(self, set_profile_card_request: "SetProfileCardRequest") -> "SetProfileCardResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def is_black_list_user(
        self, is_black_list_user_request: "IsBlackListUserRequest"
    ) -> "IsBlackListUserResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def vote_user(self, vote_user_request: "VoteUserRequest") -> "VoteUserResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_uid_by_uin(self, get_uid_by_uin_request: "GetUidByUinRequest") -> "GetUidByUinResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def get_uin_by_uid(self, get_uin_by_uid_request: "GetUinByUidRequest") -> "GetUinByUidResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def upload_private_file(
        self, private_chat_file_request: "PrivateChatFileRequest"
    ) -> "UploadPrivateChatFileResponse":
        raise grpclib.GRPCError(grpclib.const.Status.UNIMPLEMENTED)

    async def __rpc_get_friend_list(
        self,
        stream: "grpclib.server.Stream[GetFriendListRequest, GetFriendListResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_friend_list(request)
        await stream.send_message(response)

    async def __rpc_get_friend_profile_card(
        self,
        stream: "grpclib.server.Stream[GetFriendProfileCardRequest, GetFriendProfileCardResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_friend_profile_card(request)
        await stream.send_message(response)

    async def __rpc_get_stranger_profile_card(
        self,
        stream: "grpclib.server.Stream[GetStrangerProfileCardRequest, GetStrangerProfileCardResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_stranger_profile_card(request)
        await stream.send_message(response)

    async def __rpc_set_profile_card(
        self,
        stream: "grpclib.server.Stream[SetProfileCardRequest, SetProfileCardResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.set_profile_card(request)
        await stream.send_message(response)

    async def __rpc_is_black_list_user(
        self,
        stream: "grpclib.server.Stream[IsBlackListUserRequest, IsBlackListUserResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.is_black_list_user(request)
        await stream.send_message(response)

    async def __rpc_vote_user(self, stream: "grpclib.server.Stream[VoteUserRequest, VoteUserResponse]") -> None:
        request = await stream.recv_message()
        response = await self.vote_user(request)
        await stream.send_message(response)

    async def __rpc_get_uid_by_uin(
        self, stream: "grpclib.server.Stream[GetUidByUinRequest, GetUidByUinResponse]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_uid_by_uin(request)
        await stream.send_message(response)

    async def __rpc_get_uin_by_uid(
        self, stream: "grpclib.server.Stream[GetUinByUidRequest, GetUinByUidResponse]"
    ) -> None:
        request = await stream.recv_message()
        response = await self.get_uin_by_uid(request)
        await stream.send_message(response)

    async def __rpc_upload_private_file(
        self,
        stream: "grpclib.server.Stream[PrivateChatFileRequest, UploadPrivateChatFileResponse]",
    ) -> None:
        request = await stream.recv_message()
        response = await self.upload_private_file(request)
        await stream.send_message(response)

    def __mapping__(self) -> Dict[str, grpclib.const.Handler]:
        return {
            "/kritor.friend.FriendService/GetFriendList": grpclib.const.Handler(
                self.__rpc_get_friend_list,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetFriendListRequest,
                GetFriendListResponse,
            ),
            "/kritor.friend.FriendService/GetFriendProfileCard": grpclib.const.Handler(
                self.__rpc_get_friend_profile_card,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetFriendProfileCardRequest,
                GetFriendProfileCardResponse,
            ),
            "/kritor.friend.FriendService/GetStrangerProfileCard": grpclib.const.Handler(
                self.__rpc_get_stranger_profile_card,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetStrangerProfileCardRequest,
                GetStrangerProfileCardResponse,
            ),
            "/kritor.friend.FriendService/SetProfileCard": grpclib.const.Handler(
                self.__rpc_set_profile_card,
                grpclib.const.Cardinality.UNARY_UNARY,
                SetProfileCardRequest,
                SetProfileCardResponse,
            ),
            "/kritor.friend.FriendService/IsBlackListUser": grpclib.const.Handler(
                self.__rpc_is_black_list_user,
                grpclib.const.Cardinality.UNARY_UNARY,
                IsBlackListUserRequest,
                IsBlackListUserResponse,
            ),
            "/kritor.friend.FriendService/VoteUser": grpclib.const.Handler(
                self.__rpc_vote_user,
                grpclib.const.Cardinality.UNARY_UNARY,
                VoteUserRequest,
                VoteUserResponse,
            ),
            "/kritor.friend.FriendService/GetUidByUin": grpclib.const.Handler(
                self.__rpc_get_uid_by_uin,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetUidByUinRequest,
                GetUidByUinResponse,
            ),
            "/kritor.friend.FriendService/GetUinByUid": grpclib.const.Handler(
                self.__rpc_get_uin_by_uid,
                grpclib.const.Cardinality.UNARY_UNARY,
                GetUinByUidRequest,
                GetUinByUidResponse,
            ),
            "/kritor.friend.FriendService/UploadPrivateFile": grpclib.const.Handler(
                self.__rpc_upload_private_file,
                grpclib.const.Cardinality.UNARY_UNARY,
                PrivateChatFileRequest,
                UploadPrivateChatFileResponse,
            ),
        }
