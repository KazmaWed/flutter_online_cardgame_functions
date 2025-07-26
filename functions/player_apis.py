# Player-related API functions

from firebase_functions import https_fn
from firebase_admin import db
import time
import os

from utils import (
    AVATAR_MIN,
    AVATAR_MAX,
    get_and_validate_player,
    update_player_last_connected,
    validate_game_structure,
)


# Helper function to determine if running in emulator
def is_emulator():
    return os.getenv("FUNCTIONS_EMULATOR") == "true"


@https_fn.on_call(enforce_app_check=not is_emulator())
def update_name(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤー名を更新する
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/nameを更新し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # 新しい名前とgameIdを取得
        request_data = req.data or {}
        if "name" not in request_data or "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Name and gameId are required",
            )

        new_name = request_data["name"]
        game_id = request_data["gameId"]

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # 名前を更新（phaseによって場所が異なる）
        current_time = int(time.time() * 1000)
        phase = game_data.get("state", {}).get("phase", 0)

        if phase == 0:
            # phase == 0: state.config.playerInfo
            player_info_ref = (
                game_ref.child("state")
                .child("config")
                .child("playerInfo")
                .child(user_id)
            )
        else:
            # phase != 0: config.playerInfo
            player_info_ref = (
                game_ref.child("config").child("playerInfo").child(user_id)
            )

        player_info_ref.child("name").set(new_name)

        # プレイヤーのlastConnectedを更新
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("lastConnected").set(current_time)

        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Name updated successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to update name"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def update_hint(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーのヒントを更新する
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/hintを更新し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # 新しいヒントとgameIdを取得
        request_data = req.data or {}
        if "hint" not in request_data or "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Hint and gameId are required",
            )

        new_hint = request_data["hint"]
        game_id = request_data["gameId"]

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # ヒントとlastConnectedを更新
        current_time = int(time.time() * 1000)
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("hint").set(new_hint)
        player_ref.child("lastConnected").set(current_time)
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Hint updated successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to update hint"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def update_avatar(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーのアバターを更新する
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/avatarを更新し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # 新しいアバターとgameIdを取得
        request_data = req.data or {}
        if "avatar" not in request_data or "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Avatar and gameId are required",
            )

        new_avatar = request_data["avatar"]
        game_id = request_data["gameId"]

        # アバターの検証
        if new_avatar is not None:
            try:
                avatar_int = int(new_avatar)
                if avatar_int < AVATAR_MIN or avatar_int > AVATAR_MAX:
                    raise https_fn.HttpsError(
                        code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                        message="Avatar must be between 0 and 11",
                    )
                new_avatar = avatar_int
            except (ValueError, TypeError):
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                    message="Avatar must be an integer",
                )

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # アバターを更新（phaseによって場所が異なる）
        current_time = int(time.time() * 1000)
        phase = game_data.get("state", {}).get("phase", 0)

        if phase == 0:
            # phase == 0: state.config.playerInfo
            player_info_ref = (
                game_ref.child("state")
                .child("config")
                .child("playerInfo")
                .child(user_id)
            )
        else:
            # phase != 0: config.playerInfo
            player_info_ref = (
                game_ref.child("config").child("playerInfo").child(user_id)
            )

        player_info_ref.child("avatar").set(new_avatar)

        # プレイヤーのlastConnectedを更新
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("lastConnected").set(current_time)

        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Avatar updated successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to update avatar"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def submit(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーの提出時間を記録する
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/submittedに現在時刻を記録し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # gameIdを取得
        request_data = req.data or {}
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # 提出時間とlastConnectedを記録
        current_time = int(time.time() * 1000)
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("submitted").set(current_time)
        player_ref.child("lastConnected").set(current_time)
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Submit time recorded successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Failed to record submit time",
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def withdraw(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーの提出を取り消す
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/submittedをnullに設定し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # gameIdを取得
        request_data = req.data or {}
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # 提出を取り消し（submittedを削除）とlastConnectedを更新
        current_time = int(time.time() * 1000)
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("submitted").delete()
        player_ref.child("lastConnected").set(current_time)
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Submit withdrawn successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Failed to withdraw submit",
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def heartbeat(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーのハートビート（接続確認）
    gameIdを引数として受け取り、
    games/{gameId}/state/playerState/{userId}/lastConnectedを現在時刻で更新する。
    kicked==Trueの場合やgameIdが存在しない場合はエラー。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # gameIdを取得
        request_data = req.data or {}
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        # ゲームの存在確認
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤーデータ取得とkickedチェック
        try:
            get_and_validate_player(game_ref, user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # lastConnectedとgameのlastUpdatedを更新
        current_time = int(time.time() * 1000)

        # プレイヤーのlastConnectedを更新
        player_ref = game_ref.child("state").child("playerState").child(user_id)
        player_ref.child("lastConnected").set(current_time)

        # ゲームのlastUpdatedを更新
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Heartbeat updated successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Failed to update heartbeat",
        )
