import { useEffect, useState } from 'react';
import { fetchProviders } from '../api';
import { ProviderCard } from '../components/ProviderCard';
import type { Provider } from '../api';

export function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchProviders();
        setProviders(data.providers ?? []);
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
        {providers.map(p => (
          <ProviderCard
            key={p.prefix}
            name={p.name}
            prefix={p.prefix}
            models={p.models}
            status={p.status}
            errorCount={p.error_count}
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