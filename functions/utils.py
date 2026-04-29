import requests
from datetime import datetime, timedelta

API_BASE_URL = "https://portal.ixon.cloud:443/api"


def build_headers(context) -> dict:
    cfg     = context.config.get('config', {})
    secrets = context.config.get('secrets', {})
    token   = secrets.get('bearerToken', '')
    return {
        "Content-Type":    "application/json",
        "Api-Version":     "2",
        "Api-Application": cfg.get("apiApplication", ""),
        "Authorization":   f"Bearer {token}",
        "Api-Company":     cfg.get("companyId", ""),
    }


def get_data(url: str, fields: str, headers: dict, filters: str = None) -> list:
    more_after = None
    data_list  = []
    while True:
        params = {'fields': fields}
        if more_after:
            params['page-after'] = more_after
        if filters:
            params['filters'] = filters
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        body = response.json()
        data_list.extend(body["data"])
        more_after = body.get("moreAfter")
        if more_after is None:
            break
    return data_list


def list_agents(headers: dict) -> list:
    url = f"{API_BASE_URL}/agents?fields=name,publicId&page-size=4000"
    response = requests.get(url=url, headers=headers)
    response.raise_for_status()
    return response.json()["data"]


def get_data_source_id(headers: dict, agent: dict, name: str = "Databron-PLC") -> dict | None:
    data_sources = get_data(
        f"{API_BASE_URL}/agents/{agent['publicId']}/data-sources",
        "name,publicId",
        headers
    )
    matches = [ds for ds in data_sources if ds.get("name") == name]
    return matches[0] if matches else None


def get_tags_data(headers: dict, agent: dict, data_source: dict, subset: list = None) -> list:
    tag_filter = f"eq(source.publicId,\"{data_source['publicId']}\")"
    tags = get_data(
        f"{API_BASE_URL}/agents/{agent['publicId']}/data-tags",
        "tagId,name,slug",
        headers,
        tag_filter
    )
    if subset is not None:
        return [tag for tag in tags if tag.get("slug") in subset]
    return tags


def retrieve_tag_sum_json(headers: dict, data_source: dict, tags: list,
                           start: str, end: str) -> dict:
    payload = [
        {
            "source": {"publicId": data_source["publicId"]},
            "tags": [
                {
                    "id": tag["tagId"],
                    "preAggr": "raw",
                    "queries": [
                        {
                            "ref": tag["slug"],
                            "postAggr": "sum"
                        }
                    ]
                } for tag in tags
            ],
            "start": start,
            "end": end,
            "timeZone": "UTC"
        }
    ]

    response = requests.post(f"{API_BASE_URL}/data", headers=headers, json=payload)

    if response.status_code != 200:
        return {}

    tag_sums = {}
    for source_data in response.json().get("data", []):
        for point in source_data.get("points", []):
            for slug, value in point.get("values", {}).items():
                tag_sums[slug] = tag_sums.get(slug, 0) + (value or 0)

    return tag_sums

def retrieve_tag_sum_batch(headers: dict, data_source: dict, tags: list,
                            windows: list) -> list:
    """
    Fetch sums for multiple time windows in a SINGLE API call.
    windows: list of (start_str, end_str) tuples
    Returns: list of {slug: value} dicts, one per window, in same order.
    """
    payload = [
        {
            "source": {"publicId": data_source["publicId"]},
            "tags": [
                {
                    "id": tag["tagId"],
                    "preAggr": "raw",
                    "queries": [
                        {
                            "ref": f"{tag['slug']}_{i}",
                            "postAggr": "sum",
                            "start": start,
                            "end": end
                        }
                        for i, (start, end) in enumerate(windows)
                    ]
                } for tag in tags
            ],
            "timeZone": "UTC"
        }
    ]

    response = requests.post(f"{API_BASE_URL}/data", headers=headers, json=payload)

    if response.status_code != 200:
        print(f"retrieve_tag_sum_batch failed: {response.status_code} {response.text[:300]}")
        return [{} for _ in windows]

    # Build per-window results
    results = [{} for _ in windows]
    for source_data in response.json().get("data", []):
        for point in source_data.get("points", []):
            for ref, value in point.get("values", {}).items():
                # ref is like "FT_301_0", "FT_301_1" etc
                parts = ref.rsplit('_', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    slug = parts[0]
                    idx  = int(parts[1])
                    if idx < len(results):
                        results[idx][slug] = results[idx].get(slug, 0) + (value or 0)

    return results