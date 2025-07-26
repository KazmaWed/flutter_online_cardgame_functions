# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app
import json

# Import API modules
import game_apis
import player_apis
import admin_apis

# Import scheduler functions (auto-discovered by Firebase)
import creanup_workflow

# parameter in the decorator, e.g. @https_fn.on_request(max_instances=5).
set_global_options(max_instances=10)

# Initialize the Firebase app
initialize_app()

# Re-export all API functions for Firebase Functions
create_game = game_apis.create_game
enter_game = game_apis.enter_game
start_game = game_apis.start_game
reset_game = game_apis.reset_game
end_game = game_apis.end_game
exit_game = game_apis.exit_game
init_player = game_apis.init_player
get_game_config = game_apis.get_game_config
get_game_info = game_apis.get_game_info
get_value = game_apis.get_value

update_name = player_apis.update_name
update_hint = player_apis.update_hint
update_avatar = player_apis.update_avatar
submit = player_apis.submit
withdraw = player_apis.withdraw
heartbeat = player_apis.heartbeat

update_topic = admin_apis.update_topic
kick_player = admin_apis.kick_player

cleanup_scheduled = creanup_workflow.cleanup_scheduled
