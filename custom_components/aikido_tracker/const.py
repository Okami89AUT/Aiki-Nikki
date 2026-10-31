"""Konstanten des Aikido-Tracker-Bausteins."""

DOMAIN = "aikido_tracker"
VERSION = "1.2.0"
API_VERSION = 1
APP_NAME = "aikido-tracker-server"

# Einstellungen in configuration.yaml
CONF_INVITE_CODE = "invite_code"
CONF_MAX_PERSONS = "max_persons"
CONF_HISTORY_DAYS = "history_days"
CONF_DATA_DIR = "data_dir"
CONF_PAGE_FILE = "page_file"
DEFAULT_MAX_PERSONS = 20
DEFAULT_HISTORY_DAYS = 14
DEFAULT_DATA_DIRNAME = "aikido_tracker"

# Größen
MAX_DATA_BYTES = 8 * 1024 * 1024               # Datenstand je Person (serialisiert)
MAX_BODY_BYTES = MAX_DATA_BYTES + 64 * 1024    # ganze Anfrage
MAX_DRAIN_BYTES = 64 * 1024 * 1024             # so viel einer abgelehnten Anfrage wird noch gelesen und verworfen
BODY_TIMEOUT_SECONDS = 60                      # so lange darf das Lesen einer Anfrage dauern

# Namen, Codes, Datenstand
MAX_NAME_LEN = 40
MIN_CODE_LEN = 6
MAX_CODE_LEN = 64
MAX_DATA_KEYS = 30
DATA_KEY_PATTERN = r"[A-Za-z][A-Za-z0-9_]{0,40}"

# Zugangscode-Hash (scrypt)
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1

# Sperren (gleitende Zeitfenster, Sekunden)
WINDOW_FAIL = 15 * 60
LIMIT_FAIL_IP = 10          # Fehlversuche je Absender-Adresse
LIMIT_FAIL_PERSON = 30      # Fehlversuche je Person (von allen Adressen zusammen)
WINDOW_WRITE = 60
LIMIT_WRITE = 30            # Uploads je Person und Minute
WINDOW_REQUEST = 60
LIMIT_REQUEST_IP = 120      # Anfragen je Adresse und Minute (ohne ping)
MAX_TRACKED_KEYS = 10000    # Obergrenze der gemerkten Adressen/Namen je Zähler (Arbeitsspeicher)
