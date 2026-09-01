// P2-4 拆分：Accounts 页「最近一次注册会话阶段画像」子组件（v6.5.0）。
// 从原 Accounts.tsx 抽出，纯展示。

interface LiveRegistration {
  stage: string;
  stage_label: string;
  email: string;
  email_source: string;
  created_at: number;
  updated_at: number;
  last_error: string | null;
  error_category: string | null;
  stage_durations: Record<string, number>;
}

// v6.5.0: 注册阶段中文名（与后端 STAGE_LABELS 对齐）
const STAGE_LABELS_ZH: Record<string, string> = {
  init: '初始化',
  email_allocated: '分配邮箱',
  captcha_solved: '求解验证码',
  verification_sent: '发送验证',
  code_or_link_received: '收取验证链接',
  logged_in: '登录换会话',
  completed: '注册完成',
  failed: '注册失败',
};

export function LiveRegistrationCard({ reg }: { reg: LiveRegistration }) {
  return (
    <div className="accounts-detail-section tf-card">
      <div className="detail-header">
        <div className="detail-title-group">
          <h3 className="detail-title">🚀 最近一次注册会话（阶段与耗时）</h3>
          <span className="tf-badge tf-badge-info">实时</span>
        </div>
      </div>
      <div className="reg-stage-body">
        <div className="reg-stage-meta">
          <span className="reg-stage-email">{reg.email || '—'}</span>
          <span className="tf-badge tf-badge-neutral">{reg.email_source || '来源未知'}</span>
          <span
            className={`tf-badge ${
              reg.stage === 'completed'
                ? 'tf-badge-success'
                : reg.stage === 'failed'
                  ? 'tf-badge-danger'
                  : 'tf-badge-warning'
            }`}
          >
            {reg.stage_label || reg.stage}
          </span>
        </div>
        {reg.last_error && (
          <div className="reg-stage-error">⚠ {reg.last_error.slice(0, 160)}</div>
        )}
        <div className="reg-stage-flow">
          {Object.entries(reg.stage_durations ?? {}).map(([stage, dur]) => (
            <div key={stage} className="reg-stage-node">
              <div className="reg-stage-name">{STAGE_LABELS_ZH[stage] ?? stage}</div>
              <div className="reg-stage-dur">{Number(dur) >= 1 ? `${Number(dur).toFixed(1)}s` : `${(Number(dur) * 1000).toFixed(0)}ms`}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export { STAGE_LABELS_ZH };
