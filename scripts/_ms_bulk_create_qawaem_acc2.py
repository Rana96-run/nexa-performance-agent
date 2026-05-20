"""Create the Qawaem campaign on Microsoft Account 2 (187231519) via Bulk.
Same path that worked for Account 1 — campaign + ad group + keywords + negs.
RSA still pending UI (suds-enum issue on AssetLink, unresolved)."""
import sys, os, tempfile
from types import SimpleNamespace
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.v13.bulk import BulkServiceManager, EntityUploadParameters
from bingads.v13.bulk.entities import (
    BulkCampaign, BulkAdGroup, BulkKeyword, BulkCampaignNegativeKeyword,
)
from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv

load_dotenv()

DEVELOPER_TOKEN = os.getenv("MS_DEVELOPER_TOKEN")
CLIENT_ID       = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET   = os.getenv("MS_CLIENT_SECRET")
REFRESH_TOKEN   = os.getenv("MS_REFRESH_TOKEN")
ACCOUNT_ID      = int(os.getenv("MS_ACCOUNT_ID_2", "187231519"))
CUSTOMER_ID     = int(os.getenv("MS_CUSTOMER_ID_2", "254851652"))

CAMPAIGN_NAME = "Bing_Search_AR_FinancialStatemnt"
AD_GROUP_NAME = "FinancialSt_AR"

AR_KEYWORDS = [
    ("قرار وزاري 236", "Exact"),
    ("غرامة عدم إيداع القوائم المالية", "Exact"),
    ("منصة قوائم وزارة التجارة", "Exact"),
    ("إيداع القوائم المالية في السعودية", "Phrase"),
    ("غرامة التأخر في إيداع القوائم المالية", "Phrase"),
    ("عقوبة عدم إيداع القوائم المالية", "Phrase"),
    ("موعد إيداع القوائم المالية", "Phrase"),
    ("قوائم وزارة التجارة السعودية", "Phrase"),
    ("كيف أودع القوائم المالية على منصة قوائم", "Phrase"),
    ("متى يجب إيداع القوائم المالية وزارة التجارة", "Phrase"),
    ("الفرق بين قوائم وزاتكا", "Phrase"),
    ("خطوات إيداع القوائم المالية في منصة قوائم", "Phrase"),
    ("قرار 236 وزارة التجارة 1447", "Phrase"),
    ("نظام الشركات السعودي إيداع القوائم", "Phrase"),
    ("Qawaem platform Saudi Arabia", "Phrase"),
    ("Ministry of Commerce financial statements Saudi", "Phrase"),
]

NEGATIVES = [
    ("نموذج",  "Broad"), ("PDF", "Phrase"), ("تعريف", "Broad"),
    ("مفهوم",  "Broad"), ("شرح", "Broad"),  ("وظيفة", "Broad"),
    ("login",  "Phrase"), ("tutorial", "Phrase"), ("download", "Phrase"),
    ("free download", "Phrase"), ("course", "Phrase"), ("training", "Phrase"),
    ("دورة",  "Broad"), ("كورس", "Broad"),  ("تحميل", "Phrase"),
    ("مجاني", "Phrase"), ("حاسبة", "Broad"), ("غرامة محسوبة", "Phrase"),
]


def _auth():
    grant = OAuthWebAuthCodeGrant(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirection_uri=os.getenv("MS_REDIRECT_URI", "http://localhost:8080/microsoft/callback"),
    )
    grant.request_oauth_tokens_by_refresh_token(REFRESH_TOKEN)
    return AuthorizationData(
        account_id=ACCOUNT_ID, customer_id=CUSTOMER_ID,
        developer_token=DEVELOPER_TOKEN, authentication=grant,
    )


def main():
    auth = _auth()
    mgr = BulkServiceManager(
        authorization_data=auth, poll_interval_in_milliseconds=5000,
        environment="production",
    )
    camp_svc = ServiceClient(
        service="CampaignManagementService", version="v13",
        authorization_data=auth, environment="production",
    )
    f = camp_svc.factory

    # Campaign
    campaign = f.create("Campaign")
    campaign.Id           = -1
    campaign.Name         = CAMPAIGN_NAME
    campaign.Status       = "Paused"
    campaign.CampaignType = ["Search"]
    campaign.DailyBudget  = 120.0
    campaign.BudgetType   = "DailyBudgetStandard"
    campaign.TimeZone     = "KuwaitRiyadh"
    campaign.Languages    = SimpleNamespace(string=["Arabic", "English"])

    bulk_campaign = BulkCampaign()
    bulk_campaign.campaign = campaign

    # Ad group
    ag = f.create("AdGroup")
    ag.Id           = -2
    ag.Name         = AD_GROUP_NAME
    ag.Status       = "Active"
    ag.PricingModel = "Cpc"

    bulk_ag = BulkAdGroup()
    bulk_ag.campaign_id = -1
    bulk_ag.ad_group    = ag

    # Keywords
    bulk_kws = []
    for text, mt in AR_KEYWORDS:
        kw = f.create("Keyword")
        kw.Text = text; kw.MatchType = mt; kw.Status = "Active"
        bid = f.create("Bid"); bid.Amount = 2.0
        kw.Bid = bid
        b = BulkKeyword(); b.ad_group_id = -2; b.keyword = kw
        bulk_kws.append(b)

    # Negatives
    bulk_negs = []
    for text, mt in NEGATIVES:
        nk = f.create("NegativeKeyword")
        nk.Text = text; nk.MatchType = mt
        b = BulkCampaignNegativeKeyword()
        b.campaign_id = -1; b.negative_keyword = nk
        bulk_negs.append(b)

    entities = [bulk_campaign, bulk_ag] + bulk_kws + bulk_negs
    print(f"Uploading {len(entities)} entities to Acc 2 ({ACCOUNT_ID})")

    out_dir = os.path.normpath(tempfile.gettempdir())
    params = EntityUploadParameters(
        entities=entities,
        response_mode="ErrorsAndResults",
        result_file_directory=out_dir,
        result_file_name="qawaem_acc2_result.csv",
        overwrite_result_file=True,
    )
    result_entities = list(mgr.upload_entities(params))
    print(f"  result entities: {len(result_entities)}")


if __name__ == "__main__":
    main()
