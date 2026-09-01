import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchGallery, signGallery, getStoredAdminKey } from '../api';
import type { GalleryItem } from '../api';
import { Skeleton, Empty } from './Feedback';

const PWD_KEY = 'galleryPwd';
/** P2-1: 签名 URL 到期前提前重签的余量（秒）。 */
const RESIGN_LEAD_SECONDS = 5;

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
  const [loading, setLoading] = useState(true);
  const [pwdInput, setPwdInput] = useState('');
  const [pwdSubmitting, setPwdSubmitting] = useState(false);
  const [pwdWrong, setPwdWrong] = useState(false);
  const [pwdState, setPwdState] = useState<PwdState>('probing');
  const [pwdFromDashboard, setPwdFromDashboard] = useState<string | undefined>(password);
  const stored = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(PWD_KEY) ?? undefined : undefined;
  const effectivePwd = pwdFromDashboard ?? stored;
  // P2-1: 已重签过的 image_url 集合（避免同一 URL 反复触发重签形成死循环）
  const resignedRef = useRef<Set<string>>(new Set());

  /** P2-1: 用 signGallery 重签一次，然后带签名 token 刷新画廊列表。
   *  当前后端签名的是「画廊列表」而非单图 URL；若未来单图 URL 带 exp 则此函数可直接复用。 */
  const refreshSigned = useCallback(async (opts?: { isRetryOfExpired?: boolean }) => {
    try {
      const adminKey = getStoredAdminKey() || undefined;
      const signed = await signGallery(limit, adminKey);
      const pwd = extractPassword(signed.url);
      const data = await fetchGallery(limit, pwd);
      setItems(data.items ?? []);
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

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchGallery(limit, effectivePwd);
        if (cancelled) return;
        setItems(data.items ?? []);
        setPwdState('ok');
        setPwdWrong(false);
      } catch (e) {
        if (cancelled) return;
        const status = (e as any)?.status ?? (e as any)?.response?.status;
        if (status === 403) {
          sessionStorage.removeItem(PWD_KEY);
          setPwdState('required');
          if (effectivePwd) setPwdWrong(true);
        } else if (status === 401) {
          onGalleryFail?.();
        }
      }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [limit, effectivePwd, onGalleryFail]);

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
  }, [items, limit, refreshSigned]);

  const handlePwdSubmit = async () => {
    const val = pwdInput.trim();
    if (!val || pwdSubmitting) return;
    setPwdSubmitting(true);
    try {
      const data = await fetchGallery(limit, val);
      sessionStorage.setItem(PWD_KEY, val);
      setPwdFromDashboard(val);
      setItems(data.items ?? []);
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
      // 静默重拉列表：不触发任何鉴权失败重置，坏图仅可能被新列表替换
      const data = await fetchGallery(limit, effectivePwd);
      if (data?.items) setItems(data.items);
    } catch {
      // 网络抖动/瞬时失败 → 保持现状，不锁死画廊
    }
  }, [limit, effectivePwd]);

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

  if (!items.length) return <Empty text="暂无生成作品" hint="当有用户通过 API 出图成功后，作品缩略图会自动呈现在这里" />;

  return (
    <div className="gallery-modern-grid">
      {items.map((item) => (
        <div key={item.image_url || item.prompt} className="gallery-card tf-card">
          <div className="gallery-img-wrap">
            {item.image_url && (
              <img
                src={item.image_url}
                alt={item.prompt}
                loading="lazy"
                onError={() => void handleImgError(item.image_url || item.prompt)}
              />
            )}
            <div className="gallery-mask">
              <div className="gallery-prompt-text">{item.prompt}</div>
              <div className="gallery-meta-row">
                {item.duration_sec != null && (
                  <span className="gallery-badge-time">⚡ {item.duration_sec.toFixed(1)}s</span>
                )}
                <span className="gallery-badge-model">AI Generated</span>
              </div>
            </div>
          </div>
        </div>
      ))}
      <style>{`
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
        }

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
      `}</style>
    </div>
  );
}
