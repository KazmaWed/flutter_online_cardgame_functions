# Common utility functions for the card game application

from firebase_admin import db, auth
import time

# Constants

# Rate limit window in milliseconds (1 minute)
CREATION_RATE_LIMIT_WINDOW_MS = 60 * 1000
CREATION_RATE_LIMIT_THRESHOLD = 30  # Maximum game creations per rate limit window
AVATAR_MIN = 0  # Minimum avatar ID (inclusive)
AVATAR_MAX = 11  # Maximum avatar ID (inclusive)
PASSWORD_MIN = 0  # Minimum password value (4 digits, 0000 allowed)
PASSWORD_MAX = 9999  # Maximum password value (4 digits, 9999 allowed)
PASSWORD_LENGTH = 4  # Password length in digits (used for validation)
GAME_LIFESPAN = 30 * 1000  # Game lifespan in milliseconds (30 seconds of inactivity)
PLAYER_LIFESPAN = 60 * 60 * 1000  # Player lifespan in milliseconds (1 hour)
AUTH_LIFESPAN = 24 * 60 * 60 * 1000  # Auth token lifespan in milliseconds (1 day)
VALUE_MIN = 1  # Minimum value for game values (inclusive)
VALUE_MAX = 100  # Maximum value for game values (inclusive)
MAX_PLAYERS = 12  # Maximum players per game (room capacity)
ACCOUNT_COOLDOWN_MS = 4 * 1000  # New account cooldown in milliseconds (4 seconds)


def verify_auth(req):
    """
    Firebase Authenticationトークンを検証する
    """
    import os

    # エミュレーター環境の場合、デバッグ用のユーザーIDを使用
    # if os.getenv("FUNCTIONS_EMULATOR") == "true":
    #     # エミュレーター環境では、テスト用のユーザーIDを返す
    #     return "test_user_id"

    auth_header = req.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Authorization header is missing or invalid")

    token = auth_header.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token["uid"]
    except Exception as e:
        raise ValueError(f"Invalid token: {str(e)}")


def verify_game_admin(user_id: str, game_id: str):
    """
    ユーザーがゲームの管理者（最初に参加したプレイヤー）かどうかを確認する
    """
    db_ref = db.reference()
    game_ref = db_ref.child("games").child(game_id)
    game_data = game_ref.get()

    validate_game_structure(game_data)

    # playerInfoを取得し、値が一番小さいプレイヤーを特定（phaseによって場所が異なる）
    phase = game_data["state"]["phase"]
    if phase == 0:
        player_info = game_data["state"]["config"]["playerInfo"]
    else:
        player_info = game_data["config"]["playerInfo"]

    # 最小値のplayerIdを取得（entranceフィールドを使用）
    min_player_id = min(player_info, key=lambda k: player_info[k]["entrance"])
    if user_id != min_player_id:
        raise ValueError("Only the earliest joined player can perform this action")

    return True


def validate_game_structure(game_data):
    """
    ゲームの構造を検証する
    """
    if not game_data:
        raise ValueError("Game data is missing")

    # config の検証（phase によって必須性が変わる）
    config = game_data.get("config")

    # state の検証（phase を先に取得するため）
    state = game_data.get("state")
    if not state:
        raise ValueError("state is missing")

    # state.phase の検証
    phase = state.get("phase")
    if phase is None:
        raise ValueError("state.phase is required")

    # config と state.config の相互排他性を検証
    if phase == 0:
        # phase == 0: config は none であるべき
        if config is not None:
            raise ValueError("config should be None when phase == 0")
    else:
        # phase != 0: config は必須
        if not config:
            raise ValueError("config is missing when phase != 0")
        # state.config は none であるべき
        if state.get("config") is not None:
            raise ValueError("state.config should be None when phase != 0")

    # password の検証
    password = game_data.get("password")
    if password is None or password == "":
        raise ValueError("password is required")

    # values の検証（phase によって要否が変わる）
    values = game_data.get("values")
    if phase == 0:
        # phase == 0: values は none であるべき
        if values is not None:
            raise ValueError("values should be None when phase == 0")
    else:
        # phase != 0: values は必須
        if not values:
            raise ValueError("values is required when phase != 0")

    # topic の検証（phaseによって場所が異なる）
    if phase == 0:
        # phase == 0: state.config.topic (optional per schema)
        state_config = state.get("config")
        if not state_config:
            raise ValueError("state.config is missing")
        # topic is optional when phase == 0, no validation needed
    else:
        # phase != 0: config.topic (required per schema)
        if config:
            topic = config.get("topic")
            if topic is None:
                raise ValueError("config.topic is required")

    # playerInfo の検証（phaseによって場所が異なる）
    if phase == 0:
        # phase == 0: state.config.playerInfo
        state_config = state.get("config")
        if not state_config:
            raise ValueError("state.config is missing")
        player_info = state_config.get("playerInfo")
        if (
            not player_info
            or not isinstance(player_info, dict)
            or len(player_info) == 0
        ):
            raise ValueError("state.config.playerInfo must have at least one element")
        if len(player_info) > MAX_PLAYERS:
            raise ValueError(
                f"state.config.playerInfo cannot have more than {MAX_PLAYERS} elements"
            )

        # 各プレイヤー情報の構造検証
        for player_id, player_info_data in player_info.items():
            try:
                validate_player_info_structure(player_info_data)
            except ValueError as e:
                raise ValueError(f"Invalid player info for {player_id}: {str(e)}")
    else:
        # phase != 0: config.playerInfo
        if config:
            player_info = config.get("playerInfo")
            if (
                not player_info
                or not isinstance(player_info, dict)
                or len(player_info) == 0
            ):
                raise ValueError("config.playerInfo must have at least one element")
            if len(player_info) > MAX_PLAYERS:
                raise ValueError(
                    f"config.playerInfo cannot have more than {MAX_PLAYERS} elements"
                )

            # 各プレイヤー情報の構造検証
            for player_id, player_info_data in player_info.items():
                try:
                    validate_player_info_structure(player_info_data)
                except ValueError as e:
                    raise ValueError(f"Invalid player info for {player_id}: {str(e)}")

    # state.playerState の検証（最低1つ、最大MAX_PLAYERS要素が必要）
    players = state.get("playerState")
    if not players or not isinstance(players, dict) or len(players) == 0:
        raise ValueError("state.playerState must have at least one element")
    if len(players) > MAX_PLAYERS:
        raise ValueError(
            f"state.playerState cannot have more than {MAX_PLAYERS} elements"
        )

    # 各プレイヤーデータの構造検証
    for player_id, player_data in players.items():
        try:
            validate_player_structure(player_data)
        except ValueError as e:
            raise ValueError(f"Invalid player data for {player_id}: {str(e)}")

    return True


def validate_player_structure(player_data):
    """
    プレイヤーの構造を検証する（新スキーマ）
    hint: String必須（空文字OK、nullもOK）
    lastConnected: 必須
    submitted, kicked: オプショナル
    """
    if not isinstance(player_data, dict):
        raise ValueError("Player data must be a dictionary")

    # hint: 必須、String、空文字OK、nullもOK
    if "hint" not in player_data:
        raise ValueError("Player hint field is required")
    if player_data["hint"] is not None and not isinstance(player_data["hint"], str):
        raise ValueError("Player hint must be a string or null")

    # lastConnected: 必須
    if "lastConnected" not in player_data:
        raise ValueError("Player lastConnected is required")

    return True


def validate_player_info_structure(player_info_data):
    """
    プレイヤー情報の構造を検証する（新スキーマ）
    name: String必須（空文字OK）
    avatar: 必須、MIN以上MAX以下
    entrance: 必須
    """
    if not isinstance(player_info_data, dict):
        raise ValueError("Player info data must be a dictionary")

    # name: 必須、String、空文字OK
    if "name" not in player_info_data:
        raise ValueError("Player name field is required")
    if not isinstance(player_info_data["name"], str):
        raise ValueError("Player name must be a string")

    # avatar: 必須、MIN以上MAX以下
    if "avatar" not in player_info_data:
        raise ValueError("Player avatar is required")
    avatar = player_info_data["avatar"]
    if not isinstance(avatar, int) or avatar < AVATAR_MIN or avatar > AVATAR_MAX:
        raise ValueError(f"Player avatar must be between {AVATAR_MIN} and {AVATAR_MAX}")

    # entrance: 必須
    if "entrance" not in player_info_data:
        raise ValueError("Player entrance is required")

    return True


def get_and_validate_player(game_ref, user_id):
    """
    プレイヤーデータを取得し、存在確認とkickedチェックを行う
    kickedがnullまたはfalseの場合のみ成功
    """
    from firebase_admin import db

    player_ref = game_ref.child("state").child("playerState").child(user_id)
    player_data = player_ref.get()

    if not player_data:
        raise ValueError("Player not found in game")

    # プレイヤーデータ構造の検証
    try:
        validate_player_structure(player_data)
    except ValueError as e:
        raise ValueError(f"Invalid player data structure: {str(e)}")

    # kickedがnullまたはfalseの場合のみ許可
    kicked = player_data.get("kicked")
    if kicked is True:
        raise ValueError("Player has been kicked")

    return player_data


def validate_game_phase(game_data, required_phase):
    """
    ゲームのフェーズが要求されたフェーズと一致するかを厳密にチェックする
    """
    if not game_data:
        raise ValueError("Game data is missing")

    if "state" not in game_data:
        raise ValueError("Invalid game data: missing state")

    current_phase = game_data["state"].get("phase")
    if current_phase is None:
        raise ValueError("Invalid game data: missing phase")

    if current_phase != required_phase:
        raise ValueError(
            f"Invalid game phase: expected {required_phase}, got {current_phase}"
        )

    return True


def verify_account_age(user_id: str):
    """
    新規作成されたアカウントの4秒間クールダウンをチェックする
    アカウント作成から4秒以内の場合は例外を発生させる
    """
    try:
        user_record = auth.get_user(user_id)
        current_time = int(time.time() * 1000)  # Current time in milliseconds

        # アカウント作成時刻を取得
        creation_time = user_record.user_metadata.creation_timestamp

        # 4秒間のクールダウンチェック
        if current_time - creation_time < ACCOUNT_COOLDOWN_MS:
            raise ValueError(
                "Account is too new. Please wait a few seconds before using the app."
            )

    except auth.UserNotFoundError:
        raise ValueError("User account not found")


def update_player_last_connected(user_id: str):
    """
    プレイヤーのlastConnectedを現在時刻で更新する
    players/$playerId/lastConnectedフィールドを更新
    """
    current_time = int(time.time() * 1000)  # Current time in milliseconds
    db_ref = db.reference()
    player_ref = db_ref.child("players").child(user_id)
    player_ref.child("lastConnected").set(current_time)
