"""One-shot: print all workspace custom fields + project fields."""
import sys
import asana
from config import ASANA_TOKEN, ASANA_OPTIMIZATION_PROJECTS, ASANA_DAILY_PROJECTS

cfg = asana.Configuration()
cfg.access_token = ASANA_TOKEN
client = asana.ApiClient(cfg)

# Workspace fields
cf_api = asana.CustomFieldsApi(client)
WS = "1201388260892354"

print("=== WORKSPACE FIELDS ===", flush=True)
try:
    fields = list(cf_api.get_custom_fields_for_workspace(
        WS, {"limit": 100, "opt_fields": "gid,name,type,enum_options"}
    ))
    for f in fields:
        print(f"  [{f['type']}] {f['name']!r}  gid={f['gid']}", flush=True)
        for o in (f.get("enum_options") or []):
            print(f"      -> {o['name']!r}  gid={o['gid']}", flush=True)
    print(f"total: {len(fields)}", flush=True)
except Exception as e:
    print(f"  ERROR: {e}", flush=True)

# Per-project fields
proj_api = asana.ProjectsApi(client)
all_projects = {**ASANA_OPTIMIZATION_PROJECTS, **ASANA_DAILY_PROJECTS}
for key, pid in all_projects.items():
    print(f"\n=== {key} / {pid} ===", flush=True)
    try:
        p = proj_api.get_project(pid, {
            "opt_fields": (
                "custom_field_settings.custom_field.gid,"
                "custom_field_settings.custom_field.name,"
                "custom_field_settings.custom_field.type,"
                "custom_field_settings.custom_field.enum_options"
            )
        })
        for cfs in p.get("custom_field_settings", []):
            cf = cfs.get("custom_field", {})
            print(f"  [{cf.get('type')}] {cf.get('name')!r}  gid={cf.get('gid')}", flush=True)
            for o in (cf.get("enum_options") or []):
                print(f"      -> {o['name']!r}  gid={o['gid']}", flush=True)
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)

sys.stdout.flush()
