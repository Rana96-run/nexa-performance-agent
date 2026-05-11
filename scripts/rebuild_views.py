import sys; sys.stdout.reconfigure(encoding="utf-8")
from collectors.views import materialize_heavy_views
from collectors.hex_refresh import refresh_all as trigger_hex_refresh
materialize_heavy_views()
print("Views rematerialized OK")
trigger_hex_refresh()
print("Hex triggered")
