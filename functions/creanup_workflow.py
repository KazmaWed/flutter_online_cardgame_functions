from firebase_functions import https_fn
from firebase_admin import db, auth
import time
import logging

from utils import PLAYER_LIFESPAN, GAME_LIFESPAN

logger = logging.getLogger(__name__)


@https_fn.on_request()
def cleanup_scheduled(req):
    """
    Cloud Scheduler function to perform periodic cleanup of inactive data
    Runs every hour to clean up players, games, and passwords
    """
    try:
        logger.info("Starting scheduled cleanup")

        # Execute cleanup steps in order
        players_cleaned = cleanup_players()
        games_cleaned = cleanup_games()
        passwords_cleaned = cleanup_passwords()

        logger.info(
            f"Cleanup completed - Players: {players_cleaned}, Games: {games_cleaned}, Passwords: {passwords_cleaned}"
        )

        return {
            "status": "success",
            "players_cleaned": players_cleaned,
            "games_cleaned": games_cleaned,
            "passwords_cleaned": passwords_cleaned,
        }

    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        raise


def cleanup_players():
    """
    Remove players whose last API usage (lastConnected) was earlier than 1 hour ago
    Also removes their corresponding auth accounts
    """
    db_ref = db.reference()
    players_ref = db_ref.child("players")
    players_data = players_ref.get()

    if not players_data:
        return 0

    current_time = int(time.time() * 1000)  # Current time in milliseconds
    cutoff_time = current_time - PLAYER_LIFESPAN  # 1 hour ago

    players_to_remove = []

    # Check each player in the database
    for player_id, player_data in players_data.items():
        try:
            # Check lastConnected from players table
            if isinstance(player_data, dict):
                last_connected = player_data.get("lastConnected")

                # If lastConnected doesn't exist or is too old, mark for removal
                if last_connected is None or last_connected < cutoff_time:
                    players_to_remove.append(player_id)
            else:
                # If player_data is not a dict, mark for removal
                players_to_remove.append(player_id)

        except auth.UserNotFoundError:
            # If auth account doesn't exist, remove player from database
            players_to_remove.append(player_id)
        except Exception as e:
            logger.warning(f"Error checking player {player_id}: {str(e)}")

    # Remove players from database and their auth accounts
    for player_id in players_to_remove:
        # Remove from players database
        players_ref.child(player_id).delete()
        logger.info(f"Removed inactive player: {player_id}")

        # Remove auth account
        try:
            auth.delete_user(player_id)
            logger.info(f"Removed auth account: {player_id}")
        except auth.UserNotFoundError:
            logger.info(f"Auth account {player_id} already deleted")
        except Exception as e:
            logger.warning(f"Failed to remove auth account {player_id}: {str(e)}")

    # Additional auth cleanup based on last sign-in time
    auth_only_cleaned = cleanup_auth_by_signin()

    return len(players_to_remove) + auth_only_cleaned


def cleanup_auth_by_signin():
    """
    Remove anonymous auth accounts whose uid doesn't exist under players/
    This catches orphaned auth accounts that have no corresponding database entry
    """
    auth_accounts_to_remove = []

    # Get players data once for efficiency
    db_ref = db.reference()
    players_ref = db_ref.child("players")
    players_data = players_ref.get() or {}
    existing_player_ids = set(players_data.keys())

    try:
        # Get all users using pagination
        page = auth.list_users()

        while page:
            for user in page.users:
                # Check if user is anonymous (empty provider_data)
                if user.provider_data == []:
                    # If uid doesn't exist in players/, mark for removal
                    if user.uid not in existing_player_ids:
                        auth_accounts_to_remove.append(user.uid)

            # Get next page
            page = page.get_next_page()

    except Exception as e:
        logger.warning(f"Error listing users for auth cleanup: {str(e)}")
        return 0

    # Remove auth accounts
    removed_count = 0
    for user_id in auth_accounts_to_remove:
        try:
            auth.delete_user(user_id)
            logger.info(f"Removed auth account by signin time: {user_id}")
            removed_count += 1
        except auth.UserNotFoundError:
            logger.info(f"Auth account {user_id} already deleted")
        except Exception as e:
            logger.warning(f"Failed to remove auth account {user_id}: {str(e)}")

    return removed_count


def cleanup_games():
    """
    Remove games that meet cleanup criteria:
    1. lastUpdated is earlier than 30 seconds ago
    2. Games that have no players in both config/playerInfo and state/config/playerInfo
    """
    db_ref = db.reference()
    games_ref = db_ref.child("games")
    games_data = games_ref.get()

    if not games_data:
        return 0

    current_time = int(time.time() * 1000)  # Current time in milliseconds
    cutoff_time = current_time - GAME_LIFESPAN  # 30 seconds ago

    games_to_remove = []

    for game_id, game_data in games_data.items():
        if not isinstance(game_data, dict):
            continue

        should_remove = False

        # Check if lastUpdated is older than 30 seconds
        last_updated = game_data.get("lastUpdated", 0)
        if last_updated < cutoff_time:
            should_remove = True
            logger.info(f"Game {game_id} marked for removal: lastUpdated too old")

        # Check if game has no players in playerInfo
        if not should_remove:
            has_players = False

            # Check config/playerInfo (for phase != 0)
            config = game_data.get("config")
            if config and config.get("playerInfo"):
                has_players = True

            # Check state/config/playerInfo (for phase == 0)
            state = game_data.get("state")
            if state and isinstance(state, dict):
                state_config = state.get("config")
                if state_config and state_config.get("playerInfo"):
                    has_players = True

            if not has_players:
                should_remove = True
                logger.info(f"Game {game_id} marked for removal: no players")

        if should_remove:
            games_to_remove.append(game_id)

    # Remove games
    for game_id in games_to_remove:
        games_ref.child(game_id).delete()
        logger.info(f"Removed game: {game_id}")

    return len(games_to_remove)


def cleanup_passwords():
    """
    Remove passwords whose gameId doesn't exist under games/
    """
    db_ref = db.reference()
    passwords_ref = db_ref.child("passwords")
    games_ref = db_ref.child("games")

    passwords_data = passwords_ref.get()
    games_data = games_ref.get()

    if not passwords_data:
        return 0

    # Get set of existing game IDs
    existing_game_ids = set(games_data.keys()) if games_data else set()

    passwords_to_remove = []

    # Find passwords for non-existent games
    for password, game_id in passwords_data.items():
        # password_data is just the gameId string
        if isinstance(game_id, str) and game_id not in existing_game_ids:
            passwords_to_remove.append(password)

    # Remove orphaned passwords
    for password in passwords_to_remove:
        passwords_ref.child(password).delete()
        logger.info(f"Removed orphaned password: {password}")

    return len(passwords_to_remove)
