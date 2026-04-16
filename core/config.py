import os
# Settings for Shedevrum Factory Pro v.3.0

# API & Auth
SERVICE_ACCOUNT_FILE = 'service_account.json'
SHEET_NAME = 'Shedevrum_Trends'
CHROME_PROFILE_PATH = os.getenv('CHROME_PROFILE_PATH', './shedevrum_session')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'models/gemini-2.5-flash')

# Limits & Timeouts
MAX_TARGET = 20
GEN_PAUSE = 20
POST_TIMEOUT = 60
MAX_429_RETRIES = 3

# Column Mapping (1-indexed for Google Sheets)
COL_MAP = {
    'ID': 1,
    'PROMPT_ORIG': 2,
    'MODEL_ORIG': 3,
    'AUTHOR_ORIG': 4,
    'LIKES_ORIG': 5,
    'VIEWS_ORIG': 6,
    'URL_ORIG': 7,
    'IMAGE_URL_ORIG': 8,
    'DATE_ORIG': 9,
    'PROMPT_AI': 10,
    'MODEL_AI': 11,
    'AUTHOR_AI': 12,
    'LIKES_AI': 13,
    'VIEWS_AI': 14,
    'URL_AI': 15,
    'IMAGE_URL_AI': 16,
    'DATE_AI': 17,
    'STATUS': 18,
    'ASPECT_RATIO': 19,
    'ATTEMPT_COUNT': 20,
    'ERROR_LOG': 21
}

# Mapping Models
MODEL_FIXES = {
    'Alice': 'Alice AI v.1.0',
    '2.5': 'v.2.5',
    '2.7': 'v.2.7'
}
DEFAULT_MODEL = 'v.2.5'

# Paths
LOG_FILE = './logs/factory_log.txt'