// P2-4 拆分：Accounts 页「入池账号活跃明细表」子组件（虚拟滚动）。
// 从原 Accounts.tsx 抽出。useVirtualList hook 仍在 Accounts.tsx 顶层调用（hooks 顺序恒定要求），
// 本组件接收已算好的 visible / startIndex / endIndex / containerRef / onScroll / topPad / bottomPad。

import type { RefObject } from 'react';

interface AccountItem {
  email: string;
  credits: number;
  status: string;
  created_at: number | null;
  checkin_at: number | null;
  register_ip?: string | null;
  checkin_total?: number;
  checkin_cycle_day?: number;
  credits_earned_total?: number;
  credits_used_total?: number;
  images_used?: number;
  last_used_at?: number | null;
  next_claim_at?: number | null;
  age_days?: number | null;
}

interface VirtualSlice {
  visible: AccountItem[];
  startIndex: number;
  endIndex: number;
  containerRef: RefObject<HTMLDivElement | null>;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
}

export function AccountTable({
  pagedItems,
  virtualSlice,
  rowHeight,
  containerHeight,
  topPad,
  bottomPad,
}: {
  pagedItems: AccountItem[];
  virtualSlice: VirtualSlice;
  rowHeight: number;
  containerHeight: number;
  topPad: number;
  bottomPad: number;
}) {
  return (
    <div className="accounts-detail-section tf-card">
      <div className="detail-header">
        <div className="detail-title-group">
          <h3 className="detail-title">👤 入池账号活跃明细</h3>
          <span className="tf-badge tf-badge-info">{pagedItems.length} 个账号（当前页）</span>
        </div>
      </div>

      <div
        ref={virtualSlice.containerRef}
        onScroll={virtualSlice.onScroll}
        style={{ overflow: 'auto', maxHeight: containerHeight, position: 'relative' }}
      >
        <table className="tf-table">
          <thead>
            <tr>
              <th>脱敏账号邮箱</th>
              <th>剩余可用积分</th>
              <th>状态</th>
              <th>累计签到</th>
              <th>本轮第几天</th>
              <th>累计获得积分</th>
              <th>累计消耗积分</th>
              <th>出图次数</th>
              <th>存活天数</th>
              <th>入池时间</th>
              <th>上次签到时间</th>
              <th>注册IP</th>
              <th>下次签到窗口</th>
            </tr>
          </thead>
          <tbody>
            {pagedItems.length === 0 ? (
              <tr>
                <td colSpan={13} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-muted)' }}>
                  📭 暂无入库账号明细（后台持续注册激活中…）
                </td>
              </tr>
            ) : (
              <>
                {topPad > 0 && <tr aria-hidden="true" style={{ height: topPad, padding: 0 }}><td colSpan={13} style={{ padding: 0, border: 'none' }} /></tr>}
                {virtualSlice.visible.map((it) => {
                  const cTime = it.created_at
                    ? new Date(it.created_at * 1000).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : '—';
                  const chkTime = it.checkin_at
                    ? new Date(it.checkin_at * 1000).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : '尚未签到';

                  let nextChk = '今日已签';
                  const isPendingCheckin = !it.checkin_at || (Date.now() - (it.checkin_at ?? 0) * 1000 > 20 * 3600 * 1000);
                  if (isPendingCheckin) {
                    nextChk = '⚡ 待签到 (30分钟内自动触发)';
                  } else if (it.checkin_at) {
                    const nextDate = new Date(it.checkin_at * 1000 + 24 * 3600 * 1000);
                    nextChk = nextDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) + ' 之后';
                  }

                  return (
                    <tr key={it.email} style={{ height: rowHeight }}>
                      <td>
                        <code style={{ fontSize: 12, color: 'var(--primary-600)' }}>{it.email}</code>
                      </td>
                      <td>
                        <span style={{ color: 'var(--success)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                          {it.credits} 分
                        </span>
                      </td>
                      <td>
                        <span className={`tf-badge ${it.status === 'ok' ? 'tf-badge-success' : 'tf-badge-danger'}`}>
                          {it.status === 'ok' ? '正常运行' : it.status}
                        </span>
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>{it.checkin_total ?? 0} 次</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>
                        {it.checkin_total && it.checkin_total > 0 ? `${it.checkin_cycle_day ?? 0} / 7` : '—'}
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--primary-600)', fontWeight: 500 }}>
                        {it.credits_earned_total ?? 0} 分
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--danger)', fontWeight: 500 }}>
                        {it.credits_used_total ?? 0} 分
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>
                        {it.images_used ?? 0} 次
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>
                        {it.age_days != null ? `${it.age_days} 天` : '—'}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>{cTime}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>{chkTime}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>
                        {it.register_ip ? it.register_ip : '—'}
                      </td>
                      <td>
                        <span style={{
                          color: isPendingCheckin ? 'var(--warning-text)' : 'var(--text-secondary)',
                          fontWeight: isPendingCheckin ? 600 : 400,
                          fontSize: 12
                        }}>
                          {nextChk}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {bottomPad > 0 && <tr aria-hidden="true" style={{ height: bottomPad, padding: 0 }}><td colSpan={13} style={{ padding: 0, border: 'none' }} /></tr>}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export type { AccountItem };
