import { useCallback, useEffect, useRef, useState } from 'react';
import {
  signGallery,
  getStoredAdminKey,
  fetchGalleryPage,
  fetchGalleryDetail,
  downloadGalleryZip,
  softDeleteGalleryItem,
} from '../api';
import type { GalleryItem } from '../api';
import { Skeleton, Empty } from './Feedback';
import { Button } from './ui/Button';
import { notify } from '../api/core';

const PWD_KEY = 'galleryPwd';
/** P2-1: 签名 URL 到期前提前重签的余量（秒）。 */
const RESIGN_LEAD_SECONDS = 5;
/** v16 P0-3: 每页加载数量。 */
const PAGE_SIZE = 24;
/** v16 P0-3: 搜索输入防抖（毫秒），避免每击键刷列表。 */
const SEARCH_DEBOUNCE_MS = 400;

type PwdState = 'probing' | 'required' | 'ok';

/** 从 URL 解析 exp（秒级时间戳）。兼容两种落点：
 *  - `?exp=...`（后端若后续给单图 URL 直接带签名参数 */
function extractExp(url: string | null | undefined): number | null {
  if (!url) return null;
  try {
    const u = new URL(url, window.location.origin);
    const exp = u.searchParams.get('exp') ?? u.searchParams.get('e');
    if (exp) {
      const n = Number(exp);
      return Number.isFinite(n) ? n : null;
    }
    // 签名 token 紧凑格式：`password=<exp>:<sig>`（后端 _gallery_signed_url）
    const pwd = u.searchParams.get('password');
    if (pwd) {
      const expStr = pwd.split(':')[0];
      const n = Number(expStr);
      return Number.isFinite(n) ? n : null;
    }
  } catch { /* ignore malformed */ }
  return null;
}

/** 从 signGallery 返回的 URL 提取 password token（`exp:sig`），用于刷新画廊列表。 */
function extractPassword(url: string): string | undefined {
  try {
    const u = new URL(url, window.location.origin);
    return u.searchParams.get('password') ?? undefined;
  } catch { /* ignore */ }
  return undefined;
}

export function Gallery({ limit = 20, password, onGalleryFail }: {
  limit?: number;
  password?: string;
  /** P2-1: 重签/刷新因鉴权失败时回调（走父级密码重试流）。 */
  onGalleryFail?: () => void;
}) {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);  // v7.7 UX：非 401/403 错误不再伪装成"暂无作品"空态
  const [pwdInput, setPwdInput] = useState('');
  const [pwdSubmitting, setPwdSubmitting] = useState(false);
  const [pwdWrong, setPwdWrong] = useState(false);
  const [pwdState, setPwdState] = useState<PwdState>('probing');
  const [pwdFromDashboard, setPwdFromDashboard] = useState<string | undefined>(password);
  // v16 P0-3：相册化状态——多选 / 详情弹窗 / 打包下载态 / 删除确认 / 搜索 / 无限滚动
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<{ item: GalleryItem; similar: GalleryItem[] } | null>(null);
  const [zipping, setZipping] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [searchQ, setSearchQ] = useState('');           // 输入框即时值
  const [appliedSearch, setAppliedSearch] = useState(''); // 已生效的防抖搜索
  const [nextPage, setNextPage] = useState(2);
  const stored = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(PWD_KEY) ?? undefined : undefined;
  const effectivePwd = pwdFromDashboard ?? stored;
  // P2-1: 已重签过的 image_url 集合（避免同一 URL 反复触发重签形成死循环）
  const resignedRef = useRef<Set<string>>(new Set());
  // v16 P0-3: 并发守卫——观测器触发加载更多时，state 尚未提交，用 ref 防双发
  const loadingMoreRef = useRef(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const hasMore = items.length < total;

  /** P2-1: 用 signGallery 重签一次，然后带签名 token 刷新画廊列表（回到第一页）。
   *  当前后端签名的是「画廊列表」而非单图 URL；若未来单图 URL 带 exp 则此函数可直接复用。 */
  const refreshSigned = useCallback(async (opts?: { isRetryOfExpired?: boolean }) => {
    try {
      const adminKey = getStoredAdminKey() || undefined;
      const signed = await signGallery(limit, adminKey);
      const pwd = extractPassword(signed.url);
      const data = await fetchGalleryPage({ page: 1, pageSize: PAGE_SIZE, password: pwd });
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
      setNextPage(2);
      setPwdWrong(false);
    } catch (e) {
      const status = (e as any)?.status ?? (e as any)?.response?.status;
      if (status === 403 || status === 401) {
        sessionStorage.removeItem(PWD_KEY);
        setPwdState('required');
        setPwdWrong(true);
        onGalleryFail?.();
      } else if (opts?.isRetryOfExpired) {
        onGalleryFail?.();
      }
    }
  }, [limit, onGalleryFail]);

  /** v16 P0-3: 核心加载——reset=true 换页/换搜索时从第一页重建；否则追加下一页（无限滚动）。 */
  const loadPage = useCallback(async (reset: boolean, search: string, pwd: string | undefined) => {
    const targetPage = reset ? 1 : nextPage;
    if (!reset && loadingMoreRef.current) return;
    if (reset) {
      setLoading(true);
      setLoadError(null);
    } else {
      loadingMoreRef.current = true;
      setLoadingMore(true);
    }
    try {
      const data = await fetchGalleryPage({ page: targetPage, pageSize: PAGE_SIZE, search: search || undefined, password: pwd });
      setTotal(data.total ?? 0);
      if (reset) {
        setItems(data.items ?? []);
        setNextPage(2);
      } else {
        setItems(prev => {
          const seen = new Set(prev.map(it => it.id || it.image_url));
          return [...prev, ...(data.items ?? []).filter(it => !seen.has(it.id || it.image_url))];
        });
        setNextPage(targetPage + 1);
      }
      setPwdState('ok');
      setPwdWrong(false);
    } catch (e) {
      const status = (e as { status?: number })?.status ?? (e as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        sessionStorage.removeItem(PWD_KEY);
        setPwdState('required');
        if (pwd) setPwdWrong(true);
      } else if (status === 401) {
        onGalleryFail?.();
      } else if (reset) {
        // v7.7 UX：非鉴权错误（500/网络/超时）落可见错误态，而非伪装成"暂无作品"
        setLoadError(e instanceof Error ? e.message : String(e));
      } else {
        // 追加页失败不炸整屏：静默停止加载更多（用户可下拉重试 / 刷新）
        notify('加载更多失败，请稍后重试', 'error');
      }
    }
    if (reset) setLoading(false);
    else { loadingMoreRef.current = false; setLoadingMore(false); }
  }, [nextPage, onGalleryFail]);

  // 首屏加载（pwdState 变化时重建，走 reset 路径）
  const firstLoadRef = useRef(false);
  useEffect(() => {
    if (firstLoadRef.current && pwdState !== 'required') return;
    firstLoadRef.current = true;
    void loadPage(true, appliedSearch, effectivePwd);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pwdState === 'ok']);

  // v16 P0-3: 搜索防抖 → 应用后 reset 重载
  useEffect(() => {
    const t = window.setTimeout(() => {
      const q = searchQ.trim();
      if (q === appliedSearch) return;
      setAppliedSearch(q);
      void loadPage(true, q, effectivePwd);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQ]);

  // v16 P0-3: 无限滚动——哨兵元素进入视口且仍有更多时触发加载下一页
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore || loading || loadingMore) return;
    const io = new IntersectionObserver(
      entries => {
        if (entries.some(e => e.isIntersecting) && hasMore && !loadingMoreRef.current) {
          void loadPage(false, appliedSearch, effectivePwd);
        }
      },
      { rootMargin: '240px' },
    );
    io.observe(sentinel);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, loading, loadingMore, appliedSearch, items.length]);

  // P2-1: 若任一 image_url 带 exp 且即将到期（< 5s 余量），到期前自动重签刷新。
  // 当前后端返回的 image_url 不含 exp（待后端补），此 effect 不触发，由 <img onError> 防御路径兜底。
  useEffect(() => {
    if (!items.length) return;
    const now = Math.floor(Date.now() / 1000);
    let nearest = Infinity;
    let hasExp = false;
    for (const it of items) {
      const exp = extractExp(it.image_url);
      if (exp != null) {
        hasExp = true;
        if (exp < nearest) nearest = exp;
      }
    }
    if (!hasExp) return;
    // 距到期还剩不到 60s 才设近程定时器（避免长列表上挂着大量长定时器）
    const remainSec = nearest - now;
    if (remainSec > 60) return;
    const delay = Math.max(0, (nearest - RESIGN_LEAD_SECONDS - now) * 1000);
    const t = window.setTimeout(() => { void refreshSigned({ isRetryOfExpired: true }); }, delay);
    return () => window.clearTimeout(t);
  }, [items, refreshSigned]);

  const handlePwdSubmit = async () => {
    const val = pwdInput.trim();
    if (!val || pwdSubmitting) return;
    setPwdSubmitting(true);
    try {
      const data = await fetchGalleryPage({ page: 1, pageSize: PAGE_SIZE, search: appliedSearch || undefined, password: val });
      sessionStorage.setItem(PWD_KEY, val);
      setPwdFromDashboard(val);
      setItems(data.items ?? []);
      setTotal(data.total ?? 0);
      setNextPage(2);
      setPwdState('ok');
      setPwdWrong(false);
    } catch {
      setPwdWrong(true);
    }
    setPwdSubmitting(false);
  };

  /** P2-1 C2 修复：单图 <img> 加载失败时，做「静默重拉列表」而非触发鉴权流程。
   *
   *  image_url 是 R2 直链（无签名），单图 404/网络抖动 ≠ 画廊 token 过期/密码错。
   *  因此坏图只触发一次用「当前凭据」重拉列表（可能换到新 URL），一律吞错，
   *  绝不走 signGallery（开放画廊无 admin key 时必 403）→ 清密码 → 弹密码框，
   *  避免匿名/开放画廊被一张坏图锁死。签名 URL 真到期由 extractExp effect 处理。 */
  const handleImgError = useCallback(async (key: string) => {
    if (resignedRef.current.has(key)) return;
    resignedRef.current.add(key);
    try {
      // 静默重拉列表第一页：不触发任何鉴权失败重置，坏图仅可能被新列表替换
      const data = await fetchGalleryPage({ page: 1, pageSize: PAGE_SIZE, search: appliedSearch || undefined, password: effectivePwd });
      if (data?.items) setItems(data.items);
    } catch {
      // 网络抖动/瞬时失败 → 保持现状，不锁死画廊
    }
  }, [appliedSearch, effectivePwd]);

  /** v16 P0-3：任一图片项的唯一键（优先 task id，回退 image_url/prompt）。 */
  const itemKey = useCallback((it: GalleryItem): string => it.id || it.image_url || it.prompt, []);

  /** v16 P0-3：切换多选。 */
  const toggleSelect = useCallback((key: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  /** v16 P0-3：打开详情弹窗（拉取 similar 推荐，失败降级为仅本图）。 */
  const openDetail = useCallback(async (it: GalleryItem) => {
    setDetail({ item: it, similar: [] });
    if (!it.id) return;
    try {
      const d = await fetchGalleryDetail(it.id, effectivePwd, 5);
      setDetail({ item: d.item, similar: d.similar ?? [] });
    } catch {
      // 详情增强失败不阻塞弹窗展示本图
    }
  }, [effectivePwd]);

  /** v16 P0-3：打包下载选中项（Blob → 触发浏览器下载）。 */
  const handleZip = useCallback(async () => {
    const ids = [...selected].filter(Boolean);
    if (!ids.length || zipping) return;
    setZipping(true);
    try {
      const { blob, total, requested } = await downloadGalleryZip(ids, effectivePwd);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'gallery.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      // LOW（审查）：同步 revoke 可能中断部分浏览器下载，延迟到事件循环后释放
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      // 服务端按 IF_GALLERY_ZIP_BATCH 分批截断：X-Total 是实际打入张数，超出时提示分批
      notify(
        total < requested
          ? `已打包 ${total} 张（单批上限 ${requested}→${total}，请分批打包）`
          : `已打包 ${total} 张图片`,
        'success',
      );
    } catch (e) {
      notify(e instanceof Error ? e.message : '打包失败', 'error');
    }
    setZipping(false);
  }, [selected, zipping, effectivePwd]);

  /** v16 P0-3：软删选中项（可回滚：后端仅置 status=deleted）。删除前需经确认弹窗。 */
  const handleDelete = useCallback(async () => {
    const ids = [...selected].filter(Boolean);
    if (!ids.length || deleting) return;
    setDeleting(true);
    let ok = 0;
    for (const id of ids) {
      try {
        await softDeleteGalleryItem(id, effectivePwd);
        ok += 1;
      } catch { /* 单张失败跳过 */ }
    }
    // 本地移除已删项 + 清空选择 + 关确认框
    setItems(prev => prev.filter(it => !selected.has(itemKey(it))));
    setTotal(t => Math.max(0, t - ok));
    setSelected(new Set());
    setConfirmDelete(false);
    notify(`已移除 ${ok}/${ids.length} 张`, ok ? 'success' : 'error');
    setDeleting(false);
  }, [selected, effectivePwd, itemKey, deleting]);

  if (pwdState === 'probing' && loading) {
    return (
      <div className="gallery-skeleton-grid">
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <style>{`.gallery-skeleton-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }`}</style>
      </div>
    );
  }

  if (pwdState === 'required') {
    return (
      <div className="gallery-pwd-card tf-card">
        <div className="gallery-pwd-icon">🔒</div>
        <h4 className="gallery-pwd-title">画廊访问受保护</h4>
        <p className="gallery-pwd-desc">{pwdWrong ? '密码校验未通过，请重新输入' : '请输入管理员或画廊访问口令以预览生成作品'}</p>
        <div className="gallery-pwd-form">
          <input
            type="password"
            value={pwdInput}
            autoFocus
            disabled={pwdSubmitting}
            onChange={e => setPwdInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void handlePwdSubmit(); }}
            placeholder="输入画廊访问密码…"
            aria-label="画廊密码"
            className="tf-input gallery-pwd-input"
          />
          <button
            onClick={handlePwdSubmit}
            disabled={pwdSubmitting || !pwdInput.trim()}
            className="tf-btn tf-btn-primary"
          >
            {pwdSubmitting ? '验证中...' : '解锁画廊'}
          </button>
        </div>
        <style>{`
          .gallery-pwd-card {
            text-align: center;
            padding: 48px 24px;
            max-width: 440px;
            margin: 0 auto;
          }
          .gallery-pwd-icon {
            font-size: 32px;
            margin-bottom: 12px;
          }
          .gallery-pwd-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
          }
          .gallery-pwd-desc {
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 20px;
          }
          .gallery-pwd-form {
            display: flex;
            gap: 10px;
            justify-content: center;
          }
          .gallery-pwd-input {
            width: 220px;
          }
        `}</style>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="gallery-skeleton-grid">
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <Skeleton lines={1} height={200} />
        <style>{`.gallery-skeleton-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }`}</style>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="tf-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--danger-text)', background: 'var(--danger-bg)', borderColor: 'var(--danger-border)' }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🖼️</div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>画廊加载失败</div>
        <div style={{ fontSize: 12.5, opacity: 0.85, wordBreak: 'break-all' }}>{loadError}</div>
      </div>
    );
  }

  if (!items.length && !searchQ) return <Empty text="暂无生成作品" hint="当有用户通过 API 出图成功后，作品缩略图会自动呈现在这里" />;

  return (
    <div className="gallery-album">
      {/* v16 P0-3：搜索栏（prompt 子串，防抖）+ 总数 */}
      <div className="gallery-toolbar">
        <input
          type="search"
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder="搜索 prompt 关键词…"
          aria-label="搜索画廊作品"
          className="tf-input gallery-search-input"
        />
        <span className="gallery-total">{total} 张</span>
      </div>

      {!items.length && searchQ && (
        <Empty text="未找到匹配作品" hint={`没有与「${searchQ}」匹配的图片，换个关键词试试`} />
      )}

      {/* v16 P0-3：多选操作条（选中 > 0 时出现） */}
      {selected.size > 0 && (
        <div className="gallery-actionbar tf-card">
          <span className="gallery-sel-count">已选 {selected.size} 张</span>
          <div className="gallery-sel-actions">
            <Button loading={zipping} onClick={() => void handleZip()}>打包下载 ZIP</Button>
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>移除</Button>
            <Button variant="ghost" onClick={() => setSelected(new Set())}>取消选择</Button>
          </div>
        </div>
      )}

      {items.length > 0 && (
        <div className="gallery-modern-grid">
          {items.map((item) => {
            const key = itemKey(item);
            const isSel = selected.has(key);
            return (
              <div
                key={key}
                className={`gallery-card tf-card${isSel ? ' is-selected' : ''}`}
                onClick={() => void openDetail(item)}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter') void openDetail(item); }}
                aria-label={`查看作品：${item.prompt}`}
              >
                <div className="gallery-img-wrap">
                  {item.image_url && (
                    <img
                      src={item.image_url}
                      alt={item.prompt}
                      loading="lazy"
                      onError={() => void handleImgError(item.image_url || item.prompt)}
                    />
                  )}
                  {/* 多选勾选框（阻止冒泡，避免触发详情） */}
                  {item.id && (
                    <button
                      type="button"
                      className={`gallery-check${isSel ? ' checked' : ''}`}
                      aria-label={isSel ? '取消选择' : '选择'}
                      aria-pressed={isSel}
                      onClick={e => { e.stopPropagation(); toggleSelect(key); }}
                    >
                      {isSel ? '✓' : ''}
                    </button>
                  )}
                  <div className="gallery-mask">
                    <div className="gallery-prompt-text">{item.prompt}</div>
                    <div className="gallery-meta-row">
                      {item.duration_sec != null && (
                        <span className="gallery-badge-time">⚡ {item.duration_sec.toFixed(1)}s</span>
                      )}
                      <span className="gallery-badge-model">{item.model || 'AI Generated'}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* v16 P0-3：无限滚动哨兵 + 加载更多兜底按钮 */}
      <div ref={sentinelRef} className="gallery-sentinel" />
      {hasMore && (
        <div className="gallery-loadmore">
          <Button
            loading={loadingMore}
            variant="ghost"
            onClick={() => void loadPage(false, appliedSearch, effectivePwd)}
          >
            {loadingMore ? '加载中…' : `加载更多（${items.length}/${total}）`}
          </Button>
        </div>
      )}
      {!hasMore && items.length > 0 && (
        <div className="gallery-end-hint">—— 已加载全部 {total} 张 ——</div>
      )}

      {/* v16 P0-3：删除确认弹窗（软删可回滚） */}
      {confirmDelete && (
        <div
          className="gallery-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="确认移除"
          onClick={() => { if (!deleting) setConfirmDelete(false); }}
        >
          <div className="gallery-confirm" onClick={e => e.stopPropagation()}>
            <div className="gallery-confirm-title">移除 {selected.size} 张作品？</div>
            <div className="gallery-confirm-desc">将标记为已删除并从画廊隐藏（软删，可回滚，不物理删除文件）。</div>
            <div className="gallery-confirm-actions">
              <Button variant="ghost" disabled={deleting} onClick={() => setConfirmDelete(false)}>取消</Button>
              <Button variant="danger" loading={deleting} onClick={() => void handleDelete()}>确认移除</Button>
            </div>
          </div>
        </div>
      )}

      {/* v16 P0-3：详情弹窗（大图 + 元信息 + 相似推荐） */}
      {detail && (
        <div
          className="gallery-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="作品详情"
          onClick={() => setDetail(null)}
        >
          <div className="gallery-modal" onClick={e => e.stopPropagation()}>
            <button type="button" className="gallery-modal-close" aria-label="关闭" onClick={() => setDetail(null)}>×</button>
            <div className="gallery-modal-body">
              {detail.item.image_url && <img className="gallery-modal-img" src={detail.item.image_url} alt={detail.item.prompt} />}
              <div className="gallery-modal-info">
                <div className="gallery-modal-prompt">{detail.item.prompt}</div>
                <div className="gallery-modal-meta">
                  {detail.item.model && <span>模型：{detail.item.model}</span>}
                  {detail.item.aspect_ratio && <span>比例：{detail.item.aspect_ratio}</span>}
                  {detail.item.duration_sec != null && <span>耗时：{detail.item.duration_sec.toFixed(1)}s</span>}
                </div>
                {detail.similar.length > 0 && (
                  <div className="gallery-similar">
                    <div className="gallery-similar-title">相似作品</div>
                    <div className="gallery-similar-row">
                      {/* H3 容错（审查）：后端已反查补齐 id/image_url/prompt；仍缺图/缺 id 的推荐项跳过不渲染碎图 */}
                      {detail.similar.filter(s => s.image_url).map((s, i) => (
                        <img
                          key={s.id || i}
                          className="gallery-similar-thumb"
                          src={s.image_url}
                          alt={s.prompt}
                          onClick={() => void openDetail(s)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      <style>{`
        .gallery-album { position: relative; }
        .gallery-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
        .gallery-search-input { flex: 1; max-width: 320px; }
        .gallery-total { font-size: 12.5px; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
        .gallery-actionbar {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px; margin-bottom: 12px; position: sticky; top: 0; z-index: 5;
        }
        .gallery-sel-count { font-size: 13px; font-weight: 600; color: var(--text-primary); }
        .gallery-sel-actions { display: flex; gap: 8px; }
        .gallery-modern-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 14px;
        }

        .gallery-card {
          padding: 0;
          overflow: hidden;
          aspect-ratio: 1;
          cursor: pointer;
          position: relative;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .gallery-card.is-selected { outline: 2px solid var(--accent, #3b82f6); outline-offset: -2px; }

        .gallery-check {
          position: absolute; top: 8px; right: 8px; width: 24px; height: 24px;
          border-radius: 6px; border: 2px solid rgba(255,255,255,0.85);
          background: rgba(15,23,42,0.5); color: #fff; font-size: 14px; line-height: 1;
          cursor: pointer; display: flex; align-items: center; justify-content: center;
          opacity: 0; transition: opacity 0.18s ease, background 0.18s ease;
        }
        .gallery-card:hover .gallery-check, .gallery-check.checked { opacity: 1; }
        .gallery-check.checked { background: var(--accent, #3b82f6); border-color: var(--accent, #3b82f6); }

        .gallery-img-wrap {
          position: relative;
          width: 100%;
          height: 100%;
        }

        .gallery-img-wrap img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .gallery-card:hover .gallery-img-wrap img {
          transform: scale(1.08);
        }

        .gallery-mask {
          position: absolute;
          inset: 0;
          padding: 16px 14px 12px;
          background: linear-gradient(180deg, rgba(15, 23, 42, 0) 30%, rgba(15, 23, 42, 0.88) 100%);
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          opacity: 0;
          transition: opacity 0.22s ease;
        }

        .gallery-card:hover .gallery-mask {
          opacity: 1;
        }

        .gallery-prompt-text {
          font-size: 12px;
          color: #ffffff;
          line-height: 1.4;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
        }

        .gallery-meta-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 8px;
        }

        .gallery-badge-time {
          font-size: 11px;
          font-weight: 600;
          color: #34d399;
          font-family: ui-monospace, monospace;
        }

        .gallery-badge-model {
          font-size: 10px;
          color: #cbd5e1;
          background: rgba(255, 255, 255, 0.15);
          padding: 1px 6px;
          border-radius: 4px;
        }

        .gallery-sentinel { height: 1px; }

        .gallery-loadmore { display: flex; justify-content: center; padding: 18px 0 4px; }
        .gallery-end-hint {
          text-align: center; padding: 20px 0 4px;
          font-size: 12px; color: var(--text-muted, var(--text-secondary));
        }

        /* v16 P0-3：删除确认 */
        .gallery-confirm {
          background: var(--surface, #fff); border-radius: 12px; padding: 24px;
          max-width: 420px; width: 100%; box-shadow: 0 24px 64px rgba(0,0,0,0.4);
        }
        .gallery-confirm-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
        .gallery-confirm-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 18px; line-height: 1.6; }
        .gallery-confirm-actions { display: flex; gap: 10px; justify-content: flex-end; }

        /* v16 P0-3：详情弹窗 */
        .gallery-modal-backdrop {
          position: fixed; inset: 0; z-index: 50;
          background: rgba(2, 6, 23, 0.72); backdrop-filter: blur(3px);
          display: flex; align-items: center; justify-content: center; padding: 24px;
        }
        .gallery-modal {
          position: relative; background: var(--surface, #fff); border-radius: 12px;
          max-width: 900px; width: 100%; max-height: 88vh; overflow: auto;
          box-shadow: 0 24px 64px rgba(0,0,0,0.4);
        }
        .gallery-modal-close {
          position: absolute; top: 8px; right: 12px; z-index: 2; border: none; background: transparent;
          font-size: 26px; line-height: 1; cursor: pointer; color: var(--text-secondary);
        }
        .gallery-modal-body { display: flex; gap: 20px; padding: 20px; }
        .gallery-modal-img { max-width: 55%; max-height: 78vh; border-radius: 8px; object-fit: contain; }
        .gallery-modal-info { flex: 1; min-width: 0; }
        .gallery-modal-prompt { font-size: 14px; line-height: 1.6; color: var(--text-primary); margin-bottom: 12px; word-break: break-word; }
        .gallery-modal-meta { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--text-secondary); }
        .gallery-similar { margin-top: 16px; }
        .gallery-similar-title { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
        .gallery-similar-row { display: flex; gap: 8px; overflow-x: auto; }
        .gallery-similar-thumb { width: 72px; height: 72px; border-radius: 6px; object-fit: cover; cursor: pointer; flex-shrink: 0; }
        @media (max-width: 640px) {
          .gallery-modal-body { flex-direction: column; }
          .gallery-modal-img { max-width: 100%; }
        }
      `}</style>
    </div>
  );
}