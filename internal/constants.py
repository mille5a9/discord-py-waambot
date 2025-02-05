"""
This file contains constants that the bot works with.
If you wish to add or edit a constant, please make sure to comment the meaning of the constant and the reason for the edit (if applicable).
"""

CONFIRM_REACTION_EMOJI = '🟢' # Reaction emoji used to confirm actions
CANCEL_REACTION_EMOJI = '🟥' # Reaction emoji used to cancel actions
CLEAR_REACTION_EMOJI = '❌' # Reaction emoji used to clear a long response
AFFIRMATIVE_REACTION_EMOJI = '👍' # Reaction emoji used to clear a long response

CONFIRMATION_TEXT = f'*Please react to this message with {CONFIRM_REACTION_EMOJI} to continue, or react with {CANCEL_REACTION_EMOJI} to cancel. Waiting for two minutes will cancel the process automatically.*' # Message sent at the bottom of every reaction confirmaation

POSITION_MAP = {
    'QB': 1,
    'RB': 2,
    'WR': 3,
    'TE': 4,
    'D/ST': 16,
    'K': 5,
}

MONTH_ABBR_MAP = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12
}

YAHOO_FANTASY_LEAGUE_NAME = 'You Like That!'

POLL_OPTION_EMOJI = [
    '0️⃣',
    '1️⃣',
    '2️⃣',
    '3️⃣',
    '4️⃣',
    '5️⃣',
    '6️⃣',
    '7️⃣',
    '8️⃣',
    '9️⃣',
    '🔟'
]
