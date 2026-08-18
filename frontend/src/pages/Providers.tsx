import { useEffect, useState } from 'react';
import { fetchProviders } from '../api';
import { ProviderCard } from '../components/ProviderCard';
import type { ProviderSummary } from '../api';

export function ProvidersPage() {
  const [providers, setProviders] = useState<{ prefix: string; summary: ProviderSummary }[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchProviders();
        const items = Object.entries(data.items ?? {}).map(([prefix, summary]) => ({
          prefix,
          summary,
        }));
        setProviders(items);
      } catch { /* ignore */ }
    };
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>提供商状态</h1>
      <div className="prov-grid">
        {providers.map(({ prefix, summary }) => (
          <ProviderCard
            key={prefix}
            name={summary.display_name ?? prefix}
            prefix={prefix}
            models={summary.model_count ?? 0}
            status={summary.health_status ?? 'unknown'}
            errorCount={summary.error_count ?? 0}
          />
        ))}
        {!providers.length && <div className="empty">暂无数据</div>}
      </div>
      <style>{`
        .prov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
        .empty { text-align: center; color: #6b7280; padding: 40px; font-size: 13px; }
      `}</style>
    </div>
  );
}