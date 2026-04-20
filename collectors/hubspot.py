import hubspot
from hubspot.crm.contacts import ApiException
from config import HUBSPOT_TOKEN
from datetime import datetime, timedelta


def get_client():
    return hubspot.Client.create(access_token=HUBSPOT_TOKEN)


def get_sql_count(days=4):
    """
    Count Sales Qualified Leads from the Contact module.
    This is the correct signal for ad optimization - NOT Lead module.
    """
    client = get_client()
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_ms = int(cutoff.timestamp() * 1000)

    # Filter contacts with lifecyclestage = salesqualifiedlead
    # updated in the last N days
    filter_group = {
        "filters": [
            {
                "propertyName": "lifecyclestage",
                "operator": "EQ",
                "value": "salesqualifiedlead"
            },
            {
                "propertyName": "hs_lastmodifieddate",
                "operator": "GTE",
                "value": str(cutoff_ms)
            }
        ]
    }

    try:
        response = client.crm.contacts.search_api.do_search(
            public_object_search_request={
                "filterGroups": [filter_group],
                "properties": ["firstname", "hs_lead_status", "lifecyclestage",
                               "hs_analytics_source", "hs_analytics_source_data_1"],
                "limit": 100,
            }
        )
        return {
            "sql_count": response.total,
            "contacts": [
                {
                    "id": c.id,
                    "source": c.properties.get("hs_analytics_source"),
                    "source_detail": c.properties.get("hs_analytics_source_data_1"),
                }
                for c in response.results
            ]
        }
    except ApiException as e:
        print(f"HubSpot error: {e}")
        return {"sql_count": 0, "contacts": []}
