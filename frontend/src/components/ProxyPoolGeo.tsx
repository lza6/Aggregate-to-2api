import { useMemo } from 'react';
import type { ProxyPoolEntry } from '../api';

/** P3-4: 代理池地理可视化 —— 按国家聚合 emoji 分布 + 延迟/状态健康热力图。
 *
 * 纯 CSS 卡片聚合，不引重型地图依赖。输入为 fetchProxyPool 返回的 items 切片。
 * 地理归属：backend snapshot() 已为每条代理补 country / country_code / country_emoji / latency_ms。
 */
export function ProxyPoolGeo({ items }: { items: ProxyPoolEntry[] }) {
  const agg = useMemo(() => {
    const byCountry = new Map<string, { emoji: string; count: number; totalLatency: number; online: number; cooling: number }>();
    let healthy = 0, moderate = 0, slow = 0, cooling = 0, offline = 0;
    for (const it of items) {
      const key = it.country || '未知';
      const cur = byCountry.get(key) ?? { emoji: it.country_emoji || '🌐', count: 0, totalLatency: 0, online: 0, cooling: 0 };
      cur.count += 1;
      cur.totalLatency += it.latency_ms ?? 0;
      if (it.cooling) cur.cooling += 1; else cur.online += 1;
      byCountry.set(key, cur);

      if (it.cooling) { cooling += 1; continue; }
      const lat = it.latency_ms ?? 0;
      if (lat < 100) healthy += 1;
      else if (lat <= 200) moderate += 1;
      else slow += 1;
      // fails 连续失败视为离线倾向
      if ((it.fails ?? 0) > 2) offline += 1;
    }
    const countries = [...byCountry.entries()]
      .map(([name, v]) => ({ name, ...v, avgLatency: v.count ? Math.round(v.totalLatency / v.count) : 0 }))
      .sort((a, b) => b.count - a.count);
    return { countries, healthy, moderate, slow, cooling, offline };
  }, [items]);

  const total = items.length;
  const { countries, healthy, moderate, slow, cooling, offline } = agg;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
  const maxCount = Math.max(1, ...countries.map(c => c.count));

  return (
    <div className="proxy-geo-card tf-card">
      <div className="proxy-geo-header">
        <h3 className="proxy-geo-title">🌍 出口代理地理分布</h3>
        <span className="proxy-geo-total">{total} 条出口</span>
      </div>

      {/* 健康热力总览 */}
      <div className="proxy-geo-heat">
        <div className="heat-seg" style={{ flexGrow: pct(healthy), background: 'var(--success)' }} title={`健康 ${healthy}`} />
        <div className="heat-seg" style={{ flexGrow: pct(moderate), background: 'var(--warning)' }} title={`中速 ${moderate}`} />
        <div className="heat-seg" style={{ flexGrow: pct(slow), background: 'var(--danger)' }} title={`慢速 ${slow}`} />
        <div className="heat-seg" style={{ flexGrow: pct(cooling), background: 'var(--text-muted)' }} title={`冷却 ${cooling}`} />
      </div>
      <div className="proxy-geo-legend">
        <span><i style={{ background: 'var(--success)' }} />健康 {healthy} ({pct(healthy)}%)</span>
        <span><i style={{ background: 'var(--warning)' }} />中速 {moderate} ({pct(moderate)}%)</span>
        <span><i style={{ background: 'var(--danger)' }} />慢速 {slow} ({pct(slow)}%)</span>
        <span><i style={{ background: 'var(--text-muted)' }} />冷却 {cooling} ({pct(cooling)}%)</span>
        <span><i style={{ background: 'var(--danger-text)' }} />连续失败 {offline}</span>
      </div>

      {/* 国家级 emoji 分布（横向 bar） */}
      <div className="proxy-geo-countries">
        {countries.map(c => (
          <div className="geo-row" key={c.name}>
            <span className="geo-flag">{c.emoji}</span>
            <span className="geo-name">{c.name}</span>
            <div className="geo-track">
              <div className="geo-fill" style={{ width: `${Math.round((c.count / maxCount) * 100)}%` }} />
            </div>
            <span className="geo-count">{c.count} 条</span>
            <span className="geo-lat" title={`平均延迟 ${c.avgLatency}ms`}>{c.avgLatency}ms</span>
          </div>
        ))}
      </div>

      <style>{`
        .proxy-geo-card { padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; }
        .proxy-geo-header { display: flex; align-items: center; justify-content: space-between; }
        .proxy-geo-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
        .proxy-geo-total { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
        .proxy-geo-heat { display: flex; height: 12px; border-radius: var(--radius-full); overflow: hidden; background: var(--bg-subtle); }
        .heat-seg { min-width: 3px; transition: flex-grow 0.4s cubic-bezier(0.16,1,0.3,1); }
        .proxy-geo-legend { display: flex; flex-wrap: wrap; gap: 10px; font-size: 11px; color: var(--text-secondary); }
        .proxy-geo-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
        .proxy-geo-countries { display: flex; flex-direction: column; gap: 7px; }
        .geo-row { display: grid; grid-template-columns: 22px auto 1fr 48px 44px; align-items: center; gap: 8px; }
        .geo-flag { font-size: 15px; }
        .geo-name { font-size: 12px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px; }
        .geo-track { height: 10px; background: var(--bg-subtle); border-radius: var(--radius-full); overflow: hidden; }
        .geo-fill { height: 100%; background: linear-gradient(90deg, #6366f1 0%, #818cf8 100%); border-radius: var(--radius-full); transition: width 0.4s cubic-bezier(0.16,1,0.3,1); }
        .geo-count { font-size: 11.5px; color: var(--text-muted); font-variant-numeric: tabular-nums; text-align: right; }
        .geo-lat { font-size: 11px; color: var(--text-secondary); font-variant-numeric: tabular-nums; text-align: right; }
      `}</style>
    </div>
  );
}
