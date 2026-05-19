"""
Microsoft Advertising executor — campaign / ad group / keyword / RSA / extensions.

Uses CampaignManagement SOAP service via the official `bingads` SDK. Auth is
OAuth refresh-token (MS_REFRESH_TOKEN already in .env from the data-collection
side).

Mirrors a subset of executors/google_ads.py — minimum surface needed to clone
a Google Ads Search campaign onto Microsoft Ads.

Account choice: defaults to Acc1 (188176729 / customer 254476670) which has
better performance per BQ data.
"""
from __future__ import annotations

import os
from typing import Optional

from bingads.authorization import (
    AuthorizationData, OAuthWebAuthCodeGrant, OAuthTokens,
)
from bingads.service_client import ServiceClient
from dotenv import load_dotenv

load_dotenv()

DEVELOPER_TOKEN = os.getenv("MS_DEVELOPER_TOKEN")
CLIENT_ID       = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET   = os.getenv("MS_CLIENT_SECRET")
REFRESH_TOKEN   = os.getenv("MS_REFRESH_TOKEN")
ACCOUNT_ID      = int(os.getenv("MS_ACCOUNT_ID", "188176729"))
CUSTOMER_ID     = int(os.getenv("MS_CUSTOMER_ID", "254476670"))
ENVIRONMENT     = "production"


def _auth() -> AuthorizationData:
    """Refresh OAuth + build AuthorizationData."""
    if not REFRESH_TOKEN:
        raise RuntimeError("MS_REFRESH_TOKEN missing from env")

    grant = OAuthWebAuthCodeGrant(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirection_uri=os.getenv("MS_REDIRECT_URI",
                                  "http://localhost:8080/microsoft/callback"),
    )
    # Exchange refresh token → access token
    grant.request_oauth_tokens_by_refresh_token(REFRESH_TOKEN)

    return AuthorizationData(
        account_id=ACCOUNT_ID,
        customer_id=CUSTOMER_ID,
        developer_token=DEVELOPER_TOKEN,
        authentication=grant,
    )


def get_service(service_name: str, version: str = "v13"):
    """Return a ServiceClient for the named CampaignManagement service."""
    auth = _auth()
    return ServiceClient(
        service=service_name,
        version=version,
        authorization_data=auth,
        environment=ENVIRONMENT,
    )
