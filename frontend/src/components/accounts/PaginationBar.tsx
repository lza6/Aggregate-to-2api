// P2-4 拆分：Accounts 页「分页控件 + 临时邮箱池分配统计」子组件。
// 从原 Accounts.tsx 抽出，纯展示。

export function PaginationBar({
  totalItems,
  safePage,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  totalItems: number;
  safePage: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  return (
    <div className="pagination-bar">
      <span className="pagination-info">
        共 {totalItems} 条，第 {safePage}/{totalPages} 页
      </span>
      <div className="pagination-controls">
        <button
          className="tf-btn tf-btn-sm"
          disabled={safePage <= 1}
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
        >
          ◀ 上一页
        </button>
        {Array.from({ length: totalPages }, (_, i) => i + 1)
          .filter(p => p === 1 || p === totalPages || Math.abs(p - safePage) <= 2)
          .map((p, idx, arr) => (
            <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              {idx > 0 && arr[idx - 1] !== p - 1 ? <span className="pagination-ellipsis">…</span> : null}
              <button
                className={`tf-btn tf-btn-sm ${p === safePage ? 'tf-btn-primary' : ''}`}
                onClick={() => onPageChange(p)}
              >
                {p}
              </button>
            </span>
          ))}
        <button
          className="tf-btn tf-btn-sm"
          disabled={safePage >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, safePage + 1))}
        >
          下一页 ▶
        </button>
      </div>
      <select
        className="tf-input page-size-select"
        value={pageSize}
        onChange={e => onPageSizeChange(Number(e.target.value))}
      >
        <option value={10}>10条/页</option>
        <option value={20}>20条/页</option>
        <option value={50}>50条/页</option>
        <option value={100}>100条/页</option>
      </select>
    </div>
  );
}

interface EmailPoolData {
  total_registered: number;
  by_provider: Record<string, number>;
  successful_registrations?: number;
  failed_registrations?: number;
}

export function EmailPoolSection({
  emailPool,
  providerMeta,
}: {
  emailPool: EmailPoolData;
  providerMeta: Record<string, { name: string; note: string }>;
}) {
  return (
    <div className="email-pool-section tf-card">
      <div className="email-pool-header">
        <h3 className="email-pool-title">📮 临时邮箱池分配统计</h3>
        <span className="email-total-tag">注册尝试: {emailPool.total_registered} · 成功入池: {emailPool.successful_registrations ?? 0} · 失败: {emailPool.failed_registrations ?? 0}</span>
      </div>
      <div className="email-providers-list">
        {Object.entries(emailPool.by_provider ?? {}).map(([prov, n]) => (
          <div key={prov} className="email-provider-row">
            <span className="ep-name">{providerMeta[prov]?.name ?? prov}</span>
            <span className="ep-count">{n} 个邮箱</span>
          </div>
        ))}
      </div>
    </div>
  );
}
