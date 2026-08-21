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
  // probing = 探测中（可能无密码）；required = 需要密码；ok = 已通过
  const [pwdState, setPwdState] = useState<PwdState>('probing');
  const [pwdFromDashboard, setPwdFromDashboard] = useState<string | undefined>(password);
  // Dashboard 受控密码优先；否则读 sessionStorage（刷新不丢，P-GALLERY）
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
          // 密码缺失或错误：清记住态，弹框
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
      <div className="gallery-skeleton">
        <Skeleton lines={1} height={180} />
        <style>{`.gallery-skeleton { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }`}</style>
      </div>
    );
  }

  if (pwdState === 'required') {
    return <div className="gallery-pwd-required">
      <p>{pwdWrong ? '密码错误，请重新输入' : '画廊需要密码才能查看'}</p>
      <input
        type="password"
        value={pwdInput}
        autoFocus
        disabled={pwdSubmitting}
        onChange={e => setPwdInput(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') void handlePwdSubmit(); }}
        placeholder="输入画廊密码"
        aria-label="画廊密码"
      />
      <button onClick={handlePwdSubmit} disabled={pwdSubmitting || !pwdInput.trim()} className="btn">
        {pwdSubmitting ? '验证中...' : '提交'}
      </button>
      <style>{`
        .gallery-pwd-required { text-align: center; padding: 40px 0; font-size: 13px; color: #6b7280; }
        .gallery-pwd-required p { margin-bottom: 12px; }
        .gallery-pwd-required input { padding: 8px 12px; border-radius: 8px; border: 1px solid #d1d5e0; font-size: 13px; margin-right: 8px; }
        .gallery-pwd-required .btn { padding: 8px 16px; border: none; border-radius: 8px; background: #6b8aff; color: #fff; font-size: 13px; cursor: pointer; }
        .gallery-pwd-required .btn:disabled { opacity: .55; cursor: not-allowed; }
      `}</style>
    </div>;
  }

  if (loading) {
    return (
      <div className="gallery-skeleton">
        <Skeleton lines={1} height={180} />
        <style>{`.gallery-skeleton { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }`}</style>
      </div>
    );
  }
  if (!items.length) return <Empty text="暂无作品" hint="完成的生成任务会出现在这里" />;

  return (
    <div className="gallery-grid">
      {items.map((item, i) => (
        <div key={i} className="gallery-cell">
          {item.image_url && <img src={item.image_url} alt={item.prompt} loading="lazy" />}
          <div className="gallery-overlay">
            <div className="gallery-prompt">{item.prompt}</div>
            {item.duration_sec != null && <div className="gallery-dur">{item.duration_sec.toFixed(1)}s</div>}
          </div>
        </div>
      ))}
      <style>{`
        .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
        .gallery-cell { position: relative; border-radius: 10px; overflow: hidden; aspect-ratio: 1; background: #eef0f5; cursor: pointer; }
        .gallery-cell img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s; }
        .gallery-cell:hover img { transform: scale(1.06); }
        .gallery-overlay { position: absolute; inset: auto 0 0 0; padding: 20px 10px 8px; background: linear-gradient(transparent, rgba(10,14,30,.82)); color: #fff; font-size: 11px; opacity: 0; transition: opacity .25s; }
        .gallery-cell:hover .gallery-overlay { opacity: 1; }
        .gallery-prompt { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .gallery-dur { color: #a9b4d8; margin-top: 2px; }
        @media (prefers-color-scheme: dark) {
          .gallery-cell { background: #1a1d2e; }
        }
      `}</style>
    </div>
  );
}
