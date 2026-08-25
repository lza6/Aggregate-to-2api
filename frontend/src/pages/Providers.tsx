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
    return (
      <div className="providers-container">
        <div className="page-header">
          <h1 className="page-title">提供商集群状态</h1>
        </div>
        <div className="prov-grid">
          <Skeleton lines={3} height={140} />
          <Skeleton lines={3} height={140} />
          <Skeleton lines={3} height={140} />
        </div>
      </div>
    );
  }

  return (
    <div className="providers-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            提供商集群状态
            <span className="title-badge">{providers.length} 个可用上游</span>
          </h1>
          <p className="page-desc">各上游 AI 生图提供商健康度、模型目录、额度余额及官网快捷直达</p>
        </div>
        <button onClick={reload} className="tf-btn tf-btn-secondary">
          <span>🔄</span> 刷新状态
        </button>
      </div>

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
        {!providers.length && !loading && (
          <div style={{ gridColumn: '1 / -1' }}>
            <Empty text="未检测到已注册提供商" hint="后端暂未加载任何上游提供商适配器" />
          </div>
        )}
      </div>

      <style>{`
        .providers-container {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .prov-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 16px;
        }
      `}</style>
    </div>
  );
}
