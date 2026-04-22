const API_BASE = 'https://portal.ixon.cloud:443/api';

export function buildHeaders(inputs) {
  return {
    'Content-Type': 'application/json',
    'Api-Version': '2',
    'Api-Application': inputs.apiApplication || '',
    'Authorization': `Bearer ${inputs.bearerToken || ''}`,
    'Api-Company': inputs.companyId || ''
  };
}

export async function getDataSourceId(headers, agentId, name) {
  const res = await fetch(
    `${API_BASE}/agents/${agentId}/data-sources?fields=name,publicId`,
    { headers }
  );
  if (!res.ok) throw new Error(`Data source fetch failed: ${res.status}`);
  const data = await res.json();
  const ds = data.data.find(d => d.name === name);
  if (!ds) throw new Error(`Data source "${name}" not found`);
  return ds;
}

export async function getTagsData(headers, agentId, dataSource, slug) {
  const filter = `eq(source.publicId,"${dataSource.publicId}")`;
  const res = await fetch(
    `${API_BASE}/agents/${agentId}/data-tags?fields=tagId,name,slug&filters=${filter}`,
    { headers }
  );
  if (!res.ok) throw new Error(`Tags fetch failed: ${res.status}`);
  const data = await res.json();
  return data.data.filter(tag => tag.slug === slug);
}

export async function exportData(headers, dataSource, tags, start, end) {
  const body = {
    source: { publicId: dataSource.publicId },
    tags: tags.map(tag => ({
      id: tag.tagId,
      preAggr: 'raw',
      queries: [{ ref: tag.slug, offset: 0, order: 'desc' }]
    })),
    start,
    end,
    timeZone: 'UTC'
  };

  const res = await fetch(`${API_BASE}/data-export`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body)
  });

  if (!res.ok) return null;
  return await res.text();
}

export function parseCSV(csvText, tagSlug) {
  const lines = csvText.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim());
  const timeIdx = headers.indexOf('time');
  const ftIdx = headers.indexOf(tagSlug);
  if (timeIdx === -1 || ftIdx === -1) return [];

  const results = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const lastComma = line.lastIndexOf(',');
    if (lastComma === -1) continue;
    const time = line.slice(0, lastComma).trim();
    const val = line.slice(lastComma + 1).trim();
    if (time === 'time') continue;
    const flow = parseFloat(val);
    if (isNaN(flow)) continue;
    results.push({ time, flow });
  }

  results.sort((a, b) => new Date(a.time) - new Date(b.time));

  // Deduplicate: keep last value per timestamp (matching Python's groupby.last())
  const deduped = {};
  for (const r of results) {
    deduped[r.time] = r;
  }
  return Object.values(deduped);
}

export function buildChartData(points, period) {
  const SAMPLE_SECONDS = 10;

  if (!points.length) return { labels: [], barData: [], cumData: [] };

  const startTime = new Date(points[0].time).getTime();
  const endTime = new Date(points[points.length - 1].time).getTime();

  // Align to clean 10-second boundaries like pandas does
  const alignedStart = Math.floor(startTime / (SAMPLE_SECONDS * 1000)) * (SAMPLE_SECONDS * 1000);

  // Build 10-second resampled series with forward fill
  const resampled = [];
  let ptIdx = 0;
  let lastFlow = 0;

  for (let t = alignedStart; t <= endTime; t += SAMPLE_SECONDS * 1000) {
    while (ptIdx < points.length - 1 && new Date(points[ptIdx + 1].time).getTime() <= t) {
      ptIdx++;
    }
    if (new Date(points[ptIdx].time).getTime() <= t) {
      lastFlow = points[ptIdx].flow;
    }
    resampled.push({ time: t, flow: lastFlow });
  }

  // Group into display buckets based on period
  let bucketFormat;
  if (period === 'hour') bucketFormat = (t) => new Date(t).toISOString().slice(11, 16);
  else if (period === 'day') bucketFormat = (t) => new Date(t).toISOString().slice(11, 13) + ':00';
  else bucketFormat = (t) => new Date(t).toISOString().slice(0, 10);

  const barBuckets = {};
  for (const r of resampled) {
    const label = bucketFormat(r.time);
    if (!barBuckets[label]) barBuckets[label] = 0;
    barBuckets[label] += r.flow * SAMPLE_SECONDS / 1000;
  }

  const labels = Object.keys(barBuckets);
  const barData = labels.map(l => Math.round(barBuckets[l] * 1000) / 1000);
  const cumData = barData.reduce((acc, val) => {
    acc.push((acc.length ? acc[acc.length - 1] : 0) + val);
    return acc;
  }, []);

  return { labels, barData, cumData };
}

export function splitMonthly(startStr, endStr) {
  const start = new Date(startStr);
  const end = new Date(endStr);
  const intervals = [];
  let current = new Date(start);

  while (current < end) {
    let monthEnd = new Date(current.getFullYear(), current.getMonth() + 1, 1);
    monthEnd = new Date(monthEnd - 1000);
    if (monthEnd > end) monthEnd = end;
    const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
    intervals.push([fmt(current), fmt(monthEnd)]);
    current = new Date(monthEnd.getTime() + 1000);
  }

  return intervals;
}

export function getTimeRange(period) {
  const now = new Date();
  let start, end;

  if (period === 'day') {
    const yesterday = new Date(now);
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    start = new Date(Date.UTC(yesterday.getUTCFullYear(), yesterday.getUTCMonth(), yesterday.getUTCDate(), 0, 0, 0));
    end = new Date(Date.UTC(yesterday.getUTCFullYear(), yesterday.getUTCMonth(), yesterday.getUTCDate(), 23, 59, 59));
  } else if (period === 'hour') {
    start = new Date(now - 3600 * 1000);
    end = now;
  } else if (period === 'week') {
    start = new Date(now - 7 * 86400 * 1000);
    end = now;
  } else {
    start = new Date(now - 30 * 86400 * 1000);
    end = now;
  }

  const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
  return { startStr: fmt(start), endStr: fmt(end) };
}
