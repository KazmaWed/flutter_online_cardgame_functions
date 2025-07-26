# Admin-related API functions

from firebase_functions import https_fn
from firebase_admin import db
import time
import os

# Helper function to determine if running in emulator
def is_emulator():
    return os.getenv('FUNCTIONS_EMULATOR') == 'true'
from utils import (
    validate_game_phase,
    verify_game_admin,
    validate_game_structure,
    update_player_last_connected,
)


@https_fn.on_call(enforce_app_check=not is_emulator())
def update_topic(req: https_fn.CallableRequest) -> dict:
    """
    ゲームのトピックを更新する
    gameIdを引数として受け取り、games/{gameId}/config/topicを更新し、
    games/{gameId}/lastConnectedも現在時刻で更新する。
    ただし、このメソッドを実行できるのはconfig/playerInfo/{playerId}/entranceで値が一番小さいプレイヤーのみ。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        request_data = req.data or {}
        if "gameId" not in request_data or "topic" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId and topic are required",
            )

        game_id = request_data["gameId"]
        new_topic = request_data["topic"]

        # 管理者権限チェック
        verify_game_admin(user_id, game_id)

        # ゲームデータを取得
        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # ゲームのphaseをチェック（phase 0のみ許可）
        try:
            validate_game_phase(game_data, 0)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # トピックを更新
        current_time = int(time.time() * 1000)
        game_ref.child("state").child("config").child("topic").set(new_topic)
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Topic updated successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to update topic"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def kick_player(req: https_fn.CallableRequest) -> dict:
    """
    指定したプレイヤーをキックする
    gameIdとplayerIdを引数として受け取り、
    games/{gameId}/state/playerState/{playerId}/kickedをtrueにする。
    ただし、このメソッドを実行できるのはconfig/playerInfo/{playerId}/entranceで値が一番小さいプレイヤーのみ。
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        request_data = req.data or {}
        if "gameId" not in request_data or "playerId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId and playerId are required",
            )

        game_id = request_data["gameId"]
        target_player_id = request_data["playerId"]

        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()
        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # Check if user is admin
        try:
            verify_game_admin(user_id, game_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
            )

        # Check if target player exists in game
        phase = game_data["state"]["phase"]
        if phase == 0:
            player_info = game_data["state"]["config"]["playerInfo"]
        else:
            player_info = game_data["config"]["playerInfo"]

        if target_player_id not in player_info:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Target player not found in game",
            )

        # Check if target player is not the admin themselves
        if target_player_id == user_id:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Cannot kick yourself",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # Set kicked flag to true
        current_time = int(time.time() * 1000)
        game_ref.child("state").child("playerState").child(target_player_id).child(
            "kicked"
        ).set(True)
        game_ref.child("lastUpdated").set(current_time)

        return {"success": True, "message": "Player kicked successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to kick player"
        )


