# Game management API functions

from firebase_functions import https_fn
from firebase_admin import db
import random
import uuid
import time
import os
# Helper function to determine if running in emulator
def is_emulator():
    return os.getenv('FUNCTIONS_EMULATOR') == 'true'

from utils import (
    AVATAR_MAX,
    AVATAR_MIN,
    verify_game_admin,
    validate_game_structure,
    validate_game_phase,
    validate_player_structure,
    CREATION_RATE_LIMIT_WINDOW_MS,
    CREATION_RATE_LIMIT_THRESHOLD,
    PASSWORD_MIN,
    PASSWORD_MAX,
    PASSWORD_LENGTH,
    VALUE_MIN,
    VALUE_MAX,
    MAX_PLAYERS,
    update_player_last_connected,
    verify_account_age,
)


@https_fn.on_call(enforce_app_check=not is_emulator())
def create_game(req: https_fn.CallableRequest) -> dict:
    """
    新しいゲームを作成する
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # Check account age first
        try:
            verify_account_age(user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message=str(e)
            )

        # レート制限チェック
        db_ref = db.reference()
        current_time = int(time.time() * 1000)
        player_ref = db_ref.child("players").child(user_id)
        player_data = player_ref.get() or {}

        # TTL期限内でのゲーム作成数をチェック
        creation_count = player_data.get("creationCount", 0)
        creation_count_ttl = player_data.get("creationCountTtl", 0)

        # TTLが切れている場合はリセット
        if current_time > creation_count_ttl:
            creation_count = 0

        if creation_count >= CREATION_RATE_LIMIT_THRESHOLD:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.RESOURCE_EXHAUSTED,
                message=f"Rate limit exceeded. You can create at most {CREATION_RATE_LIMIT_THRESHOLD} games per {CREATION_RATE_LIMIT_WINDOW_MS // 1000} seconds",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # ゲームIDと4桁パスワードを生成し、トランザクションで登録
        game_id = str(uuid.uuid4())
        max_retry = 5
        for _ in range(max_retry):
            password_int = random.randint(PASSWORD_MIN, PASSWORD_MAX)
            password = f"{password_int:04d}"
            password_ref = db_ref.child("passwords").child(password)

            def txn_password(current_value):
                if current_value is not None:
                    return https_fn.Abort()
                return game_id

            try:
                result = password_ref.transaction(txn_password)
                if result is not None:
                    # 登録成功
                    break
            except Exception:
                pass
        else:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.ALREADY_EXISTS,
                message="Failed to generate unique password after several attempts",
            )

        # ゲームデータの作成
        game_data = {
            "password": password,
            "state": {
                "config": {
                    "topic": "",
                    "playerInfo": {
                        user_id: {
                            "name": "",
                            "avatar": random.randint(AVATAR_MIN, AVATAR_MAX),
                            "entrance": current_time,
                        }
                    },
                },
                "phase": 0,
                "playerState": {
                    user_id: {
                        "hint": "",
                        "lastConnected": current_time,
                    }
                },
            },
            "lastUpdated": current_time,
        }

        # データベースにゲームデータを保存
        db_ref.child("games").child(game_id).set(game_data)

        # プレイヤーのcurrentGameIdを更新
        db_ref.child("players").child(user_id).child("currentGameId").set(game_id)

        # プレイヤーの作成カウンターを更新
        new_creation_count = creation_count + 1
        new_creation_count_ttl = current_time + CREATION_RATE_LIMIT_WINDOW_MS
        player_ref.child("creationCount").set(new_creation_count)
        player_ref.child("creationCountTtl").set(new_creation_count_ttl)

        # 成功レスポンス
        return {"success": True, "gameId": game_id, "password": password}

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
            message=f"Failed to create game: {str(e)}",
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def enter_game(req: https_fn.CallableRequest) -> dict:
    """
    ゲームに参加する（パスワードを使用）
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # Check account age first
        try:
            verify_account_age(user_id)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message=str(e)
            )

        # リクエストデータの取得と検証
        request_data = req.data or {}
        if "password" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Password is required",
            )

        password = request_data["password"]

        # パスワードの形式チェック（4桁の文字列）
        if (
            not isinstance(password, str)
            or len(password) != PASSWORD_LENGTH
            or not password.isdigit()
        ):
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message=f"Password must be a {PASSWORD_LENGTH}-digit string",
            )

        # パスワードからゲームIDを取得
        db_ref = db.reference()
        game_id = db_ref.child("passwords").child(password).get()

        if not game_id:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Invalid password",
            )

        # ゲームデータを取得
        game_data = db_ref.child("games").child(game_id).get()

        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # プレイヤー数の上限チェック
        current_players = game_data.get("state", {}).get("playerState", {})
        if len(current_players) >= MAX_PLAYERS:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.RESOURCE_EXHAUSTED,
                message="Game is full",
            )

        # 既に参加済みかチェック
        if user_id in current_players:
            # 既に参加済みの場合、lastConnectedを更新
            current_time = int(time.time() * 1000)
            game_ref = db_ref.child("games").child(game_id)

            # lastConnectedを更新
            player_ref = game_ref.child("state").child("playerState").child(user_id)
            player_ref.child("lastConnected").set(current_time)

            # phase == 0 の場合のみentranceを更新
            phase = game_data.get("state", {}).get("phase", 0)
            if phase == 0:
                # entranceを更新
                player_info_ref = (
                    game_ref.child("state")
                    .child("config")
                    .child("playerInfo")
                    .child(user_id)
                )
                player_info_ref.child("entrance").set(current_time)

            game_ref.child("lastUpdated").set(current_time)
            db_ref.child("players").child(user_id).child("currentGameId").set(game_id)
            return {"success": True, "gameId": game_id}

        # 新しいプレイヤーの場合、phase 0のみ許可
        try:
            validate_game_phase(game_data, 0)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="New players can only join during matching phase (phase 0)",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # 新しいプレイヤーを排他制御で追加
        current_time = int(time.time() * 1000)
        player_data = {
            "hint": "",
            "lastConnected": current_time,
        }
        player_info = {
            "name": "",
            "avatar": random.randint(AVATAR_MIN, AVATAR_MAX),
            "entrance": current_time,
        }
        game_ref = db_ref.child("games").child(game_id)
        players_ref = game_ref.child("state").child("playerState")

        def txn_add_player(current_players):
            if current_players is None:
                current_players = {}
            if user_id in current_players:
                return https_fn.Abort()  # 既に参加済み
            if len(current_players) >= MAX_PLAYERS:
                return https_fn.Abort()  # 定員超過
            current_players[user_id] = player_data
            return current_players

        try:
            result = players_ref.transaction(txn_add_player)
            if result is None or user_id not in result:
                raise https_fn.HttpsError(
                    code=https_fn.FunctionsErrorCode.RESOURCE_EXHAUSTED,
                    message="Game is full or already joined",
                )
        except https_fn.HttpsError:
            raise
        except Exception:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INTERNAL,
                message="Failed to join game",
            )

        # state/config/playerInfo, lastUpdated, currentGameIdは通常通り更新
        game_ref.child("state").child("config").child("playerInfo").child(user_id).set(
            player_info
        )
        game_ref.child("lastUpdated").set(current_time)
        db_ref.child("players").child(user_id).child("currentGameId").set(game_id)

        return {"success": True, "gameId": game_id, "password": password}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        # More detailed error for debugging
        import traceback

        error_details = (
            f"Failed to enter game: {str(e)}\nTraceback: {traceback.format_exc()}"
        )
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message=error_details
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def start_game(req: https_fn.CallableRequest) -> dict:
    """
    ゲームを開始する
    gameIdを引数として受け取り、games/{gameId}/state/phaseを0から1に変更する。
    valuesにプレイヤー数だけエントリーを持つ辞書を追加（key=playerId, value=1-100のユニーク整数）
    このメソッドを実行できるのはconfig/playerInfo/{playerId}/entranceで値が一番小さいプレイヤーのみ。
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
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

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

        # phase が 0 の場合のみ実行可能
        try:
            validate_game_phase(game_data, 0)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # Check if game has players
        players = game_data["state"]["playerState"]

        # 1-100のユニーク整数を生成
        available_values = list(range(VALUE_MIN, VALUE_MAX + 1))
        random.shuffle(available_values)

        # プレイヤーごとに値を割り当て
        values = {}
        for i, player_id in enumerate(players.keys()):
            values[player_id] = available_values[i]

        # ゲームの状態を更新（一括更新）
        current_time = int(time.time() * 1000)

        # state/config から config へのデータ移動
        state_player_info = game_data["state"]["config"]["playerInfo"]
        state_topic = game_data["state"]["config"]["topic"]

        # 一括更新で全ての変更を適用
        game_ref.update(
            {
                "config/playerInfo": state_player_info,
                "config/topic": state_topic,
                "state/config": None,  # state.config を削除
                "state/phase": 1,
                "values": values,
                "lastUpdated": current_time,
            }
        )

        return {"success": True, "message": "Game started successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to start game"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def end_game(req: https_fn.CallableRequest) -> dict:
    """
    ゲームを終了する
    gameIdを引数として受け取り、games/{gameId}/state/phaseを2に変更する。
    このメソッドを実行できるのはconfig/playerInfo/{playerId}/entranceで値が一番小さいプレイヤーのみ。
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
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

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

        # phase が 1 の場合のみ実行可能
        try:
            validate_game_phase(game_data, 1)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, message=str(e)
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # ゲームの状態を更新
        current_time = int(time.time() * 1000)
        game_ref.update(
            {
                "state/phase": 2,
                "lastUpdated": current_time,
            }
        )

        return {"success": True, "message": "Game ended successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to end game"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def reset_game(req: https_fn.CallableRequest) -> dict:
    """
    ゲームをリセットする
    gameIdを引数として受け取り、ゲームをphase 0に戻す。
    各プレイヤーのhintとsubmittedを削除し、valuesを削除する。
    このメソッドを実行できるのはconfig/playerInfo/{playerId}/entranceで値が一番小さいプレイヤーのみ。
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
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

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

        # Get current players and config info
        phase = game_data["state"]["phase"]

        # phase が 1 または 2 の場合のみ実行可能
        if phase not in [1, 2]:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Game can only be reset during active phases (phase 1 or 2)",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        current_time = int(time.time() * 1000)

        # Prepare the reset data
        update_data = {
            "state/phase": 0,
            "lastUpdated": current_time,
            "values": None,  # Remove values
        }

        # Phase 1 or 2: players info in config/playerInfo, need to move back to state/config
        player_info = game_data["config"]["playerInfo"]
        topic = game_data["config"]["topic"]

        # Move config back to state/config
        update_data["state/config/topic"] = topic
        update_data["state/config/playerInfo"] = player_info
        update_data["config"] = None  # Remove config

        # Reset playerState: remove hint and submitted for all players
        player_states = game_data["state"]["playerState"]
        for player_id in player_states:
            # Clear hint and submitted, keep lastConnected and kicked status
            update_data[f"state/playerState/{player_id}/hint"] = ""
            update_data[f"state/playerState/{player_id}/submitted"] = None

        # Apply all changes atomically
        game_ref.update(update_data)

        return {"success": True, "message": "Game reset successfully"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to reset game"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def exit_game(req: https_fn.CallableRequest) -> dict:
    """
    ゲームから退出する
    gameIdを引数として受け取り、games/{gameId}/state/playerState/{userId}を削除し、
    games/{gameId}/lastUpdatedを現在時刻で更新する。
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
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        if not game_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Game not found",
            )

        # プレイヤーが実際にゲームに参加しているかチェック
        players = game_data.get("state", {}).get("playerState", {})
        if user_id not in players:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Player not in game",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # プレイヤーをゲームから削除（排他制御）
        players_ref = game_ref.child("state").child("playerState")

        def txn_remove_player(current_players):
            if current_players is None or user_id not in current_players:
                return https_fn.Abort()
            del current_players[user_id]
            return current_players

        try:
            updated_players = players_ref.transaction(txn_remove_player)
        except Exception:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INTERNAL,
                message="Failed to exit game (transaction error)",
            )

        # 全てのプレイヤー関連データを削除
        phase = game_data.get("state", {}).get("phase", 0)

        # playerInfoを削除
        if phase == 0:
            game_ref.child("state").child("config").child("playerInfo").child(
                user_id
            ).delete()
        else:
            game_ref.child("config").child("playerInfo").child(user_id).delete()

        # valuesからも削除（存在する場合）
        values = game_data.get("values", {})
        if user_id in values:
            game_ref.child("values").child(user_id).delete()

        # currentGameIdを削除
        db_ref.child("players").child(user_id).child("currentGameId").delete()

        # 残りプレイヤーがいない場合、ゲームを削除
        if not updated_players or len(updated_players) == 0:
            # ゲームを削除
            game_ref.delete()
            # パスワードマッピングも削除
            password = game_data.get("password")
            if password:
                db_ref.child("passwords").child(str(password)).delete()

        return {"success": True, "message": "Successfully exited game"}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to exit game"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def init_player(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーを初期化し、現在のゲームIDを返す
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # Use auth.uid directly
        uid = user_id

        db_ref = db.reference()

        # Check players/$uid/currentGameId
        current_game_id = (
            db_ref.child("players").child(uid).child("currentGameId").get()
        )

        if not current_game_id:
            return {"success": True, "gameId": None}

        # Check if games/$currentGame exists
        game_ref = db_ref.child("games").child(current_game_id)
        game_data = game_ref.get()

        if not game_data:
            # Game doesn't exist, cleanup currentGameId
            db_ref.child("players").child(uid).child("currentGameId").delete()
            return {"success": True, "gameId": None}

        # Check if games/$currentGame/lastUpdated is older than 30 seconds
        current_time = int(time.time() * 1000)
        last_updated = game_data.get("lastUpdated", 0)

        from utils import GAME_LIFESPAN

        if current_time - last_updated > GAME_LIFESPAN:
            # Game is too old, cleanup currentGameId
            db_ref.child("players").child(uid).child("currentGameId").delete()
            return {"success": True, "gameId": None}

        # Check if games/$currentGame/state/playerState/$uid exists
        player_in_game = game_data.get("state", {}).get("playerState", {}).get(uid)

        if not player_in_game:
            # Player not in game, cleanup currentGameId
            db_ref.child("players").child(uid).child("currentGameId").delete()
            return {"success": True, "gameId": None}

        # Validate player data structure
        try:
            validate_player_structure(player_in_game)
        except ValueError:
            # Invalid player data structure, cleanup currentGameId
            db_ref.child("players").child(uid).child("currentGameId").delete()
            return {"success": True, "gameId": None}

        # Check if player is kicked
        if player_in_game.get("kicked", False):
            # Player is kicked, cleanup currentGameId
            db_ref.child("players").child(uid).child("currentGameId").delete()
            return {"success": True, "gameId": None}

        # All validations passed, return gameId
        return {"success": True, "gameId": current_game_id}

    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Failed to initialize player",
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def get_game_config(req: https_fn.CallableRequest) -> dict:
    """
    ゲームの設定と値を取得する
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        player_id = req.auth.uid

        # gameIdを取得
        request_data = req.data or {}
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        db_ref = db.reference()

        # Check if games/$gameId exists
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        if not game_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Game not found"
            )

        # Check if games/$gameId/lastUpdated is older than 30 seconds
        current_time = int(time.time() * 1000)
        last_updated = game_data.get("lastUpdated", 0)

        from utils import GAME_LIFESPAN

        if current_time - last_updated > GAME_LIFESPAN:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.DEADLINE_EXCEEDED,
                message="Game expired",
            )

        # Check if games/$gameId/state/playerState/$playerId exists
        player_in_game = (
            game_data.get("state", {}).get("playerState", {}).get(player_id)
        )

        if not player_in_game:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Player not in game"
            )

        # Check if player is kicked
        if player_in_game.get("kicked", False):
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
                message="Player has been kicked",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(player_id)

        # Get game state and config
        game_state = game_data.get("state", {})
        game_config = game_data.get("config", {})
        phase = game_state.get("phase", 0)
        values = game_data.get("values", {})

        # Determine what values to return based on phase
        if phase >= 2:
            # Phase 2 or higher: return all values
            return_values = values
        else:
            # Phase less than 2: return only the current player's value
            return_values = (
                {player_id: values.get(player_id)} if player_id in values else {}
            )

        # Return success response
        return {
            "success": True,
            "values": return_values,
            "config": game_config,
        }

    except ValueError as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED, message=str(e)
        )
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Failed to get game config",
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def get_value(req: https_fn.CallableRequest) -> dict:
    """
    プレイヤーの値を取得する
    """
    try:
        # For callable functions, use req.auth.uid directly
        if not req.auth:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
                message="Authentication required",
            )

        user_id = req.auth.uid

        # リクエストデータの取得
        request_data = req.data or {}
        if "gameId" not in request_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="gameId is required",
            )

        game_id = request_data["gameId"]

        db_ref = db.reference()
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        # ゲームの存在確認
        if not game_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Game not found"
            )

        # ゲーム構造の検証
        try:
            validate_game_structure(game_data)
        except ValueError as e:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT, message=str(e)
            )

        # phase != 0 でのみ値を取得可能
        if game_data["state"]["phase"] == 0:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
                message="Values are not available during matching phase",
            )

        # プレイヤーがゲームに参加しているかチェック
        players = game_data["state"]["playerState"]
        if user_id not in players:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Player not found in game",
            )

        # プレイヤーがキックされていないかチェック
        player_data = players[user_id]
        if player_data.get("kicked", False):
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
                message="Player has been kicked from the game",
            )

        # valuesの存在確認
        values = game_data.get("values", {})
        if user_id not in values:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND,
                message="Value not assigned to player",
            )

        # ゲームの期限切れチェック
        current_time = int(time.time() * 1000)
        last_updated = game_data.get("lastUpdated", 0)
        from utils import GAME_LIFESPAN

        if current_time - last_updated > GAME_LIFESPAN:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.DEADLINE_EXCEEDED,
                message="Game has expired",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # 値を返す
        player_value = values[user_id]
        return {"success": True, "gameId": game_id, "value": player_value}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to get value"
        )


@https_fn.on_call(enforce_app_check=not is_emulator())
def get_game_info(req: https_fn.CallableRequest) -> dict:
    """
    ゲーム情報を取得する
    gameIdを引数として受け取り、gameIdとpasswordを返す。
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

        db_ref = db.reference()

        # Check if games/$gameId exists
        game_ref = db_ref.child("games").child(game_id)
        game_data = game_ref.get()

        if not game_data:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Game not found"
            )

        # Check if games/$gameId/lastUpdated is older than 30 seconds
        current_time = int(time.time() * 1000)
        last_updated = game_data.get("lastUpdated", 0)

        from utils import GAME_LIFESPAN

        if current_time - last_updated > GAME_LIFESPAN:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.DEADLINE_EXCEEDED,
                message="Game expired",
            )

        # Check if games/$gameId/state/playerState/$playerId exists
        player_in_game = game_data.get("state", {}).get("playerState", {}).get(user_id)

        if not player_in_game:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Player not in game"
            )

        # Check if player is kicked
        if player_in_game.get("kicked", False):
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
                message="Player has been kicked",
            )

        # Update last connected in players/$playerId
        update_player_last_connected(user_id)

        # Get password
        password = game_data.get("password")

        return {"success": True, "gameId": game_id, "password": password}

    except https_fn.HttpsError:
        # Re-raise HttpsError as-is
        raise
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL, message="Failed to get game info"
        )
