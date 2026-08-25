import { useEffect, useState } from 'react';
import { fetchProviders } from '../api';
import { ProviderCard } from '../components/ProviderCard';
import { Skeleton, Empty, ErrorRetry } from '../components/Feedback';
import { useApi } from '../hooks/useApi';
import type { ProviderSummary } from '../api';

export function ProvidersPage() {
  const { data, loading, error, reload } = useApi(() => fetchProviders(), { intervalMs: 10000 });
  const [providers, setProviders] = useState<{ prefix: string; summary: ProviderSummary }[]>([]);

  useEffect(() => {
    if (data) {
      setProviders(Object.entries(data.items ?? {}).map(([prefix, summary]) => ({ prefix, summary })));
    }
  }, [data]);

  if (error && !data) return <ErrorRetry message={error.message} onRetry={reload} />;
  if (loading && !data) {
    return <div className="prov-grid"><Skeleton lines={2} height={110} /><Skeleton lines={2} height={110} /></div>;
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>提供商状态</h1>
      <div className="prov-grid">
        {providers.map(({ prefix, summary }) => (
          <ProviderCard
            key={prefix}
            name={summary.display_name ?? prefix}
            prefix={prefix}
            baseUrl={summary.base_url}
            models={summary.model_count ?? 0}
            status={summary.health_status ?? 'unknown'}
            errorCount={summary.error_count ?? 0}
            credits={summary.credits}
          />
        ))}
        {!providers.length && !loading && <Empty text="暂无数据" hint="后端未注册任何提供商" />}
      </div>
      <style>{`
        .prov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
      `}</style>
    </div>
  );
}
