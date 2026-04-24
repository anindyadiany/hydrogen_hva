from ixoncdkingress.function.context import FunctionContext
from functions.utils import build_headers, get_data_source_id, get_tags_data, retrieve_bucketed_data
from datetime import datetime

HYDROGEN_FLOW_TAG = 'FT_301'

# Cache data source and tags so we don't look them up every call
_cache = {}


@FunctionContext.expose
def get_production(context: FunctionContext, **kwargs):
    agent_id = kwargs.get('agentId', '')
    ds_name = kwargs.get('dataSourceName', 'Databron-PLC')
    tag_slug = kwargs.get('tagSlug', HYDROGEN_FLOW_TAG)
    start_ms = kwargs.get('startMs')
    end_ms = kwargs.get('endMs')

    if not agent_id:
        return {'error': 'Agent ID not configured'}

    headers = build_headers(context)

    # Cache data source and tags lookup
    cache_key = f"{agent_id}:{ds_name}:{tag_slug}"
    if cache_key not in _cache:
        data_source = get_data_source_id(headers, agent_id, ds_name)
        tags = get_tags_data(headers, agent_id, data_source, subset=[tag_slug])
        if not tags:
            return {'error': f'Tag "{tag_slug}" not found'}
        _cache[cache_key] = {'data_source': data_source, 'tags': tags}

    data_source = _cache[cache_key]['data_source']
    tags = _cache[cache_key]['tags']

    start_str = datetime.utcfromtimestamp(start_ms / 1000).strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = datetime.utcfromtimestamp(end_ms / 1000).strftime('%Y-%m-%dT%H:%M:%SZ')

    span_ms = end_ms - start_ms
    result = retrieve_bucketed_data(headers, data_source, tags, start_str, end_str, span_ms)
    result['error'] = None

    return result
