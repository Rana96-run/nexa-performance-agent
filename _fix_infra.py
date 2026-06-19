import json, sys

f = "n8n/workflows/infra_data_collection.json"
with open(f, encoding="utf-8") as fp:
    wf = json.load(fp)

REMOVE_IDS = {
    "a716f778-51cb-5b55-9102-5d0184997b11",  # HubSpot Leads (contacts API)
    "6c4e2c0d-aa37-58af-bade-8a8239afb020",  # Map · HubSpot
    "b98d7390-f370-4fc9-b2b0-2728b0849e60",  # Error Skip · HubSpot
}

# Collect actual names of nodes being removed
removed_names = set()
surviving_nodes = []
for node in wf["nodes"]:
    nid = node.get("id", "")
    nm = node.get("name", "")
    if nid in REMOVE_IDS:
        removed_names.add(nm)
        print(f"  REMOVING node: {nm!r} (id={nid})")
    else:
        surviving_nodes.append(node)

print(f"Nodes before: {len(wf['nodes'])}, after: {len(surviving_nodes)}")
wf["nodes"] = surviving_nodes

# Remove connections whose source is a removed node
# Also strip edges pointing to removed nodes from surviving sources
new_connections = {}
for src_name, out_data in wf.get("connections", {}).items():
    if src_name in removed_names:
        print(f"  REMOVING connection source: {src_name!r}")
        continue
    new_out = {}
    for port, port_edges in out_data.items():
        new_port = []
        for edge_list in port_edges:
            new_edge_list = [e for e in edge_list if e.get("node") not in removed_names]
            new_port.append(new_edge_list)
        new_out[port] = new_port
    new_connections[src_name] = new_out

wf["connections"] = new_connections
print("Connections cleaned")

# Merge All Channels: reduce numberInputs from 6 to 5 (HubSpot no longer feeds it)
for node in wf["nodes"]:
    if node.get("name") == "Merge All Channels":
        old = node.get("parameters", {}).get("numberInputs")
        node["parameters"]["numberInputs"] = 5
        print(f"  Merge All Channels numberInputs: {old} -> 5")

# Build All MERGE SQLs: remove the hubspot aggregation+MERGE section from JS
for node in wf["nodes"]:
    if node.get("id") == "build-all-merge-sqls-001":
        js = node["parameters"]["jsCode"]
        # The hubspot section starts with the comment marker
        hub_marker = "\n// ── HUBSPOT"
        if hub_marker in js:
            idx = js.index(hub_marker)
            end_marker = "\nreturn results;"
            end_idx = js.index(end_marker, idx)
            removed_len = end_idx - idx
            js = js[:idx] + js[end_idx:]
            node["parameters"]["jsCode"] = js
            print(f"  Removed hubspot MERGE section from Build All MERGE SQLs ({removed_len} chars)")
        else:
            # Try alternate marker
            hub_marker2 = "HUBSPOT"
            if hub_marker2 in js:
                print(f"  WARNING: exact marker not found; found HUBSPOT at pos {js.index(hub_marker2)}")
                print(f"  Context: {js[js.index(hub_marker2)-20:js.index(hub_marker2)+60]!r}")
            else:
                print(f"  WARNING: no HUBSPOT marker found in Build All MERGE SQLs")
        break

# Query HS Recon: update to use Lead Module API (0-136) instead of contacts
for node in wf["nodes"]:
    if node.get("id") == "7e67fafa-57bc-511b-bdbf-34afa9e51e2d":
        old_url = node["parameters"].get("url", "")
        print(f"  Query HS Recon OLD url: {old_url}")
        node["parameters"]["url"] = "https://api.hubapi.com/crm/v3/objects/0-136/search"
        node["parameters"]["method"] = "POST"
        node["parameters"]["sendBody"] = True
        node["parameters"]["specifyBody"] = "json"
        node["parameters"]["jsonBody"] = (
            "={{ JSON.stringify({ "
            "filterGroups:[{ filters:[{ propertyName:'hs_createdate', operator:'GTE', "
            "value:String(new Date($('Trigger').first().json.start_7d).getTime()) }]}], "
            "properties:['hs_createdate'], limit:1 }) }}"
        )
        print(f"  Query HS Recon UPDATED to Lead Module API (0-136)")
        break

# Reconcile BQ vs HS: update to use .total from HubSpot Lead Module search response
for node in wf["nodes"]:
    if node.get("id") == "a0cd3ed1-df9c-541f-9a32-4cd1dcfd91b5":
        old_js = node["parameters"]["jsCode"]
        new_js = old_js.replace(
            "const hsTotal = ($('Query HS Recon').first().json?.results||[]).length || 0;",
            "const hsTotal = $('Query HS Recon').first().json?.total || 0;"
        )
        if new_js != old_js:
            node["parameters"]["jsCode"] = new_js
            print("  Reconcile BQ vs HS: updated HS total extraction to use .total from Lead Module")
        else:
            print(f"  WARNING: Reconcile BQ vs HS JS pattern not matched")
            # Show relevant section
            idx = old_js.find("hsTotal")
            if idx >= 0:
                print(f"  Actual text: {old_js[idx:idx+80]!r}")
        break

with open(f, "w", encoding="utf-8") as fp:
    json.dump(wf, fp, indent=4, ensure_ascii=False)
print("infra_data_collection.json written OK")
