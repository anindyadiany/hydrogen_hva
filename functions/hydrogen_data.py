from ixoncdkingress.function.context import FunctionContext
from functions.utils import build_headers, get_data_source_id, get_tags_data, list_agents, retrieve_tag_sum_json
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


HYDROGEN_FLOW_TAG = 'FT_301'
SAMPLE_SECONDS = 10

_cache = {}

@FunctionContext.expose
def get_agents(context: FunctionContext, **kwargs):
    """Only return agents that have the Databron-PLC data source."""
    headers = build_headers(context)
    all_agents = list_agents(headers)
    
    valid = []
    for a in all_agents:
        agent = {'publicId': a['publicId']}
        ds = get_data_source_id(headers, agent, 'Databron-PLC')
        if ds is not None:
            valid.append({'id': a['publicId'], 'name': a['name']})
    
    return {'agents': valid}

@FunctionContext.expose
def get_production(context: FunctionContext, **kwargs):
    agent_id  = kwargs.get('agentId', '')
    ds_name   = kwargs.get('dataSourceName', 'Databron-PLC')
    tag_slug  = kwargs.get('tagSlug', HYDROGEN_FLOW_TAG)
    start_ms  = kwargs.get('startMs')
    end_ms    = kwargs.get('endMs')

    if not agent_id:
        return {'error': 'Agent ID not configured'}
    if start_ms is None or end_ms is None:
        return {'error': 'startMs and endMs are required'}

    headers = build_headers(context)
    agent   = {'publicId': agent_id}

    cache_key = f"{agent_id}:{ds_name}:{tag_slug}"
    if cache_key not in _cache:
        data_source = get_data_source_id(headers, agent, ds_name)
        if data_source is None:
            return {'error': f'Data source "{ds_name}" not found for this agent'}
        tags = get_tags_data(headers, agent, data_source, subset=[tag_slug])
        if not tags:
            return {'error': f'Tag "{tag_slug}" not found'}
        ft301_tag = next(
            (t for t in tags if t.get('slug') == tag_slug or tag_slug in t.get('slug', '')),
            None
        )
        if ft301_tag is None:
            return {'error': f'Tag {tag_slug} not found'}
        _cache[cache_key] = {
            'data_source': data_source,
            'tags': tags,
            'slug': ft301_tag['slug']
        }

    data_source = _cache[cache_key]['data_source']
    tags        = _cache[cache_key]['tags']
    slug        = _cache[cache_key]['slug']

    start_dt     = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end_dt       = datetime.fromtimestamp(end_ms   / 1000, tz=timezone.utc)
    bucket_start = start_dt.replace(minute=0, second=0, microsecond=0)

    # Build list of (index, bucket_start, bucket_end) tuples
    buckets = []
    current = bucket_start
    while current < end_dt:
        bucket_end = min(current + timedelta(hours=1), end_dt)
        buckets.append((current, bucket_end))
        current = bucket_end

    # Fetch all buckets in parallel
    def fetch_bucket(bucket):
        start, end = bucket
        tag_sums = retrieve_tag_sum_json(
            headers=headers,
            data_source=data_source,
            tags=tags,
            start=start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            end=end.strftime('%Y-%m-%dT%H:%M:%SZ')
        )
        kg = round(float(tag_sums[slug]) * SAMPLE_SECONDS / 1000, 3) if tag_sums and slug in tag_sums else 0.0
        return (start, kg)

    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_bucket, b): b for b in buckets}
        for future in as_completed(futures):
            start, kg = future.result()
            results[start] = kg

    # Sort by time to ensure correct order
    labels   = []
    bar_data = []
    for start, _ in buckets:
        kg = results.get(start, 0.0)
        labels.append(start.strftime('%d %b %H:%M'))
        bar_data.append(kg)

    total_kg = round(sum(bar_data), 3)

    cum_data = []
    running = 0.0
    for v in bar_data:
        running += v
        cum_data.append(round(running, 3))

    return {
        'totalKg': total_kg,
        'labels':  labels,
        'barData': bar_data,
        'cumData': cum_data,
        'error':   None
    }