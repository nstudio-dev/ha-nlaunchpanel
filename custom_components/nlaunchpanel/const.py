"""Constantes de l'intégration NLaunchPanel."""

from datetime import timedelta

DOMAIN = "nlaunchpanel"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_PERSISTENT = "persistent_notifications"

# Un tour toutes les 60 s : l'état, les ressources, les sauvegardes, les mises
# à jour d'image de chaque instance, et la cloche.
SCAN_INTERVAL = timedelta(seconds=60)

# Les appels simultanés vers le panel pendant un tour.
MAX_PARALLEL = 4

# L'événement que reçoit chaque nouvelle notification de la cloche.
EVENT_NOTIFICATION = "nlaunchpanel_notification"

# Les états d'une instance que le panel rend.
STATUSES = ["running", "stopped", "deploying", "starting", "stopping", "restarting", "failed", "crashed", "created"]
