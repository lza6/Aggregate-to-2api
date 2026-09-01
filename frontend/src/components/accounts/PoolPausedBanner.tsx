// P2-4 拆分：Accounts 页「号池停用横幅 + 占位卡」子组件（v6.9.1 号池停用）。
// 从原 Accounts.tsx 抽出，props 驱动（poolPaused + onToggle），纯展示。

export function PoolPausedBanner({
  poolPaused,
  onToggle,
}: {
  poolPaused: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <div className={`pool-paused-banner ${poolPaused ? 'is-paused' : ''}`}>
        <div className="pool-paused-main">
          <span className="pool-paused-icon">⏸</span>
          <div className="pool-paused-text">
            <div className="pool-paused-title">
              {poolPaused ? '号池自动补号已暂停' : '号池自动补号运行中'}
            </div>
            <div className="pool-paused-desc">
              {poolPaused
                ? 'NanoBanana Pro 每日签到号池已停用（自动补号/签到会话卡片不展示），后端能力保留，可随时恢复'
                : '号池已恢复展示，自动补号/签到会话与明细表正常显示'}
            </div>
          </div>
        </div>
        <button
          className="tf-btn tf-btn-sm"
          onClick={onToggle}
          title="切换号池停用状态"
        >
          {poolPaused ? '▸ 展开明细' : '▾ 折叠明细（停用号池）'}
        </button>
      </div>

      {poolPaused && (
        <div className="pool-grid">
          <div className="pool-disabled-placeholder tf-card">
            <span className="pool-disabled-icon">⏸</span>
            <div>
              <div className="pool-disabled-title">号池管理已停用</div>
              <div className="pool-disabled-desc">NanoBanana Pro（每日签到）自动补号暂停，达标率/补号速率/签到会话卡片不展示。后端能力保留，可点击上方「展开明细」恢复查看</div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
