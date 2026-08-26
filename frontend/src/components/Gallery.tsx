import { useEffect, useState } from 'react';
import { fetchGallery } from '../api';
import type { GalleryItem } from '../api';
import { Skeleton, Empty } from './Feedback';

const PWD_KEY = 'galleryPwd';

type PwdState = 'probing' | 'required' | 'ok';

export function Gallery({ limit = 20, password }: { limit?: number; password?: string }) {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pwdInput, setPwdInput] = useState('');
  const [pwdSubmitting, setPwdSubmitting] = useState(false);
  const [pwdWrong, setPwdWrong] = useState(false);
  const [pwdState, setPwdState] = useState<PwdState>('probing');
  const [pwdFromDashboard, setPwdFromDashboard] = useState<string | undefined>(password);
  const stored = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(PWD_KEY) ?? undefined : undefined;
  const effectivePwd = pwdFromDashboard ?? stored;

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
        }
      }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [limit, effectivePwd]);

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
            {item.image_url && <img src={item.image_url} alt={item.prompt} loading="lazy" />}
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
