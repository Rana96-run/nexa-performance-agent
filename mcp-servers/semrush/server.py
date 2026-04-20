"""
SEMrush MCP Server
Exposes SEMrush API as tools for Claude Code.
"""

import csv
import io
import os
import httpx
from mcp.server.fastmcp import FastMCP

SEMRUSH_API_KEY = os.environ.get("SEMRUSH_API_KEY", "")
BASE_URL = "https://api.semrush.com/"

mcp = FastMCP("semrush", instructions="SEMrush SEO & paid media intelligence tools for domain analysis, keyword research, competitor gaps, and backlink data.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_csv(text: str) -> list[dict]:
    """Parse SEMrush semicolon-delimited CSV response into list of dicts."""
    if not text or text.startswith("ERROR"):
        return [{"error": text.strip()}]
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    return [row for row in reader]


async def _call(params: dict) -> list[dict]:
    """Make a request to the SEMrush API."""
    params["key"] = SEMRUSH_API_KEY
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        return _parse_csv(resp.text)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def domain_overview(domain: str, database: str = "us") -> list[dict]:
    """
    Get a high-level overview of a domain's organic & paid search presence.
    Returns: organic keywords count, organic traffic, organic cost, paid keywords, paid traffic, paid cost, backlinks count.

    Args:
        domain: Domain to analyze (e.g. "qoyod.com")
        database: Regional database code (us, uk, sa, ae, etc.)
    """
    return await _call({
        "type": "domain_ranks",
        "domain": domain,
        "database": database,
        "export_columns": "Db,Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
    })


@mcp.tool()
async def domain_organic_keywords(
    domain: str,
    database: str = "us",
    limit: int = 20,
    sort: str = "tr_desc",
) -> list[dict]:
    """
    Get organic search keywords a domain ranks for.
    Returns: keyword, position, search volume, CPC, URL, traffic %, traffic cost, competition, results count.

    Args:
        domain: Domain to analyze
        database: Regional database code (us, uk, sa, ae, etc.)
        limit: Number of results (max 10000)
        sort: Sort order — tr_desc (traffic desc), po_asc (position asc), nq_desc (volume desc)
    """
    return await _call({
        "type": "domain_organic",
        "domain": domain,
        "database": database,
        "display_limit": str(limit),
        "display_sort": sort,
        "export_columns": "Ph,Po,Nq,Cp,Ur,Tr,Tc,Co,Nr",
    })


@mcp.tool()
async def domain_paid_keywords(
    domain: str,
    database: str = "us",
    limit: int = 20,
    sort: str = "tr_desc",
) -> list[dict]:
    """
    Get paid search keywords a domain is bidding on.
    Returns: keyword, position, search volume, CPC, URL, traffic %, traffic cost, competition.

    Args:
        domain: Domain to analyze
        database: Regional database code
        limit: Number of results (max 10000)
        sort: Sort order
    """
    return await _call({
        "type": "domain_adwords",
        "domain": domain,
        "database": database,
        "display_limit": str(limit),
        "display_sort": sort,
        "export_columns": "Ph,Po,Nq,Cp,Ur,Tr,Tc,Co",
    })


@mcp.tool()
async def keyword_overview(
    keywords: str,
    database: str = "us",
) -> list[dict]:
    """
    Get overview data for one or more keywords (volume, CPC, competition, results).
    Separate multiple keywords with semicolons (max 100).

    Args:
        keywords: Keyword phrase(s) separated by semicolons (e.g. "accounting software;e-invoicing saudi")
        database: Regional database code
    """
    return await _call({
        "type": "phrase_all",
        "phrase": keywords,
        "database": database,
        "export_columns": "Ph,Nq,Cp,Co,Nr,Td",
    })


@mcp.tool()
async def keyword_difficulty(
    keywords: str,
    database: str = "us",
) -> list[dict]:
    """
    Get keyword difficulty scores for one or more keywords.
    Score 0-100: higher = harder to rank.

    Args:
        keywords: Keyword phrase(s) separated by semicolons
        database: Regional database code
    """
    return await _call({
        "type": "phrase_kdi",
        "phrase": keywords,
        "database": database,
        "export_columns": "Ph,Kd",
    })


@mcp.tool()
async def keyword_related(
    keyword: str,
    database: str = "us",
    limit: int = 20,
    sort: str = "nq_desc",
) -> list[dict]:
    """
    Get related keywords for a seed keyword (for keyword expansion).
    Returns: keyword, volume, CPC, competition, results count, trend.

    Args:
        keyword: Seed keyword
        database: Regional database code
        limit: Number of results
        sort: Sort order — nq_desc (volume desc), cp_desc (CPC desc)
    """
    return await _call({
        "type": "phrase_related",
        "phrase": keyword,
        "database": database,
        "display_limit": str(limit),
        "display_sort": sort,
        "export_columns": "Ph,Nq,Cp,Co,Nr,Td",
    })


@mcp.tool()
async def domain_competitors(
    domain: str,
    database: str = "us",
    limit: int = 10,
) -> list[dict]:
    """
    Find a domain's top organic search competitors.
    Returns: competitor domain, common keywords, SE keywords, SE traffic, SE traffic cost.

    Args:
        domain: Domain to analyze
        database: Regional database code
        limit: Number of competitors to return
    """
    return await _call({
        "type": "domain_organic_organic",
        "domain": domain,
        "database": database,
        "display_limit": str(limit),
        "export_columns": "Dn,Np,Or,Ot,Oc,Ad",
    })


@mcp.tool()
async def keyword_gap(
    domains: str,
    database: str = "us",
    limit: int = 20,
    sort: str = "nq_desc",
) -> list[dict]:
    """
    Compare keyword profiles across up to 5 domains (keyword gap analysis).
    Use pipe-separated domains. Prefix with + (organic), - (paid), or * (both).
    Example: "+qoyod.com|+competitor1.com|+competitor2.com"

    Args:
        domains: Pipe-separated domains with prefixes (e.g. "+qoyod.com|+xero.com")
        database: Regional database code
        limit: Number of results
        sort: Sort order
    """
    return await _call({
        "type": "domain_domains",
        "domains": domains,
        "database": database,
        "display_limit": str(limit),
        "display_sort": sort,
        "export_columns": "Ph,Nq,Cp,Co",
    })


@mcp.tool()
async def backlinks_overview(
    target: str,
    target_type: str = "root_domain",
) -> list[dict]:
    """
    Get backlinks overview for a domain or URL.
    Returns: total backlinks, referring domains, referring IPs, follow/nofollow counts, authority score.

    Args:
        target: Domain, subdomain, or URL to analyze
        target_type: "root_domain", "domain", or "url"
    """
    return await _call({
        "type": "backlinks_overview",
        "target": target,
        "target_type": target_type,
        "export_columns": "total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,nofollows_num,score,trust_score",
    })


@mcp.tool()
async def backlinks_referring_domains(
    target: str,
    target_type: str = "root_domain",
    limit: int = 20,
) -> list[dict]:
    """
    Get top referring domains linking to a target.
    Returns: referring domain, backlinks count, follow/nofollow, first/last seen.

    Args:
        target: Domain or URL to analyze
        target_type: "root_domain", "domain", or "url"
        limit: Number of results
    """
    return await _call({
        "type": "backlinks_refdomains",
        "target": target,
        "target_type": target_type,
        "display_limit": str(limit),
        "export_columns": "domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen",
    })


@mcp.tool()
async def domain_ad_copies(
    domain: str,
    database: str = "us",
    limit: int = 10,
) -> list[dict]:
    """
    Get ad copy texts used by a domain in paid search.
    Returns: ad title, description, visible URL, keyword.

    Args:
        domain: Domain to analyze
        database: Regional database code
        limit: Number of results
    """
    return await _call({
        "type": "domain_adwords_unique",
        "domain": domain,
        "database": database,
        "display_limit": str(limit),
        "export_columns": "Ph,Tt,Ds,Vu,Ur,Po",
    })


if __name__ == "__main__":
    mcp.run()
