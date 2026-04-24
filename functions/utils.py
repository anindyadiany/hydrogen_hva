import requests
from datetime import datetime, timedelta

API_BASE_URL = "https://portal.ixon.cloud:443/api"


def build_headers(context):
    """Build API headers from Cloud Function config instead of configfile.ini."""
    return {
        'Content-Type': 'application/json',
        'Api-Version': '2',
        'Api-Application': context.config['apiApplication'],
        'Authorization': f"Bearer {context.config['bearerToken']}",
        'Api-Company': context.config['companyId']
    }


def get_data(url, fields, headers, filters=None):
    """Paginated GET."""
    more_after = None
    data_list = []

    while True:
        params = f"?fields={fields}"
        if more_after:
            params += f"&page-after={more_after}"
        if filters:
            params += f"&filters={filters}"

        response = requests.get(f"{url}{params}", headers=headers)
        data = response.json()["data"]
        data_list.extend(data)
        more_after = response.json().get("moreAfter")

        if more_after is None:
            break

    return data_list


def get_data_source_id(headers, agent_id, name="Databron-PLC"):
    """Find a data source by name."""
    data_sources = get_data(
        f"{API_BASE_URL}/agents/{agent_id}/data-sources",
        'name,publicId', headers
    )
    for ds in data_sources:
        if ds.get('name') == name:
            return ds
    raise Exception(f'Data source "{name}" not found')


def get_tags_data(headers, agent_id, data_source, subset=None):
    """Get tags, optionally filtered by slug list."""
    tag_filter = f'eq(source.publicId,"{data_source["publicId"]}")'
    tags = get_data(
        f"{API_BASE_URL}/agents/{agent_id}/data-tags",
        'tagId,name,slug', headers, tag_filter
    )
    if subset is not None:
        return [tag for tag in tags if tag.get('slug') in subset]
    return tags


def retrieve_tag_sum_json(headers, data_source, tags, start, end):
    """Get sum of tag values for a time range."""
    payload = [
        {
            "source": {"publicId": data_source['publicId']},
            "tags": [
                {
                    "id": tag['tagId'],
                    "preAggr": "raw",
                    "queries": [
                        {
                            "ref": tag['slug'],
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

    response = requests.post(
        f"{API_BASE_URL}/data",
        headers=headers,
        json=payload
    )

    if response.status_code != 200:
        return {}

    result = response.json()
    tag_sums = {}
    for source_data in result.get('data', []):
        for point in source_data.get('points', []):
            for slug, value in point.get('values', {}).items():
                tag_sums[slug] = tag_sums.get(slug, 0) + (value or 0)

    return tag_sums


def retrieve_bucketed_data(headers, data_source, tags, start, end, span_ms):
    """Get pre-bucketed data from IXON — no CSV parsing needed."""
    SAMPLE_SECONDS = 10

    if span_ms <= 3600 * 1000:
        step = 60
    elif span_ms <= 86400 * 1000:
        step = 3600
    else:
        step = 86400

    payload = [
        {
            "source": {"publicId": data_source['publicId']},
            "tags": [
                {
                    "id": tag['tagId'],
                    "preAggr": "raw",
                    "queries": [
                        {
                            "ref": tag['slug'],
                            "postAggr": "sum",
                            "step": step
                        }
                    ]
                } for tag in tags
            ],
            "start": start,
            "end": end,
            "timeZone": "UTC"
        }
    ]

    response = requests.post(
        f"{API_BASE_URL}/data",
        headers=headers,
        json=payload
    )

    if response.status_code != 200:
        return {'labels': [], 'barData': [], 'cumData': [], 'totalKg': 0}

    result = response.json()
    slug = tags[0]['slug']

    labels = []
    bar_data = []

    for source_data in result.get('data', []):
        for point in source_data.get('points', []):
            timestamp = point.get('time', '')
            value = point.get('values', {}).get(slug, 0) or 0

            if step <= 60:
                label = timestamp[11:16]
            elif step <= 3600:
                label = timestamp[11:13] + ':00'
            else:
                label = timestamp[0:10]

            kg = round(float(value) * SAMPLE_SECONDS / 1000, 3)
            labels.append(label)
            bar_data.append(kg)

    cum_data = []
    total = 0
    for v in bar_data:
        total += v
        cum_data.append(round(total, 3))

    total_kg = cum_data[-1] if cum_data else 0

    return {
        'labels': labels,
        'barData': bar_data,
        'cumData': cum_data,
        'totalKg': round(total_kg, 3)
    }
