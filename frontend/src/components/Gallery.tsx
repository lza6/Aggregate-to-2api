import { useEffect, useState } from 'react';
import { fetchGallery } from '../api';
import type { GalleryItem } from '../api';

export function Gallery({ limit = 20, password }: { limit?: number; password?: string }) {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pwdInput, setPwdInput] = useState('');
  const [pwdRequired, setPwdRequired] = useState(false);

  useEffect(() => {
    const load = async () => {
      if (password === undefined) return;
      setLoading(true);
      try {
        const data = await fetchGallery(limit, password);
        setItems(data.items ?? []);
        setPwdRequired(false);
      } catch (e) {
        if ((e as any)?.status === 403) setPwdRequired(true);
      }
      setLoading(false);
    };
    load();
  }, [limit, password]);

  const handlePwdSubmit = () => {
    // 父组件通过回调处理密码提交
  };

  if (pwdRequired) {
    return <div className="gallery-pwd-required">
      <p>画廊需要密码才能查看</p>
      <input type="password" value={pwdInput} onChange={e => setPwdInput(e.target.value)} placeholder="输入画廊密码" />
    </div>;
  }
  if (loading) return <div className="gallery-loading">加载中...</div>;
  if (!items.length) return <div className="gallery-empty">暂无作品</div>;

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
        .gallery-loading, .gallery-empty { text-align: center; padding: 40px 0; font-size: 13px; color: #6b7280; }
        @media (prefers-color-scheme: dark) {
          .gallery-cell { background: #1a1d2e; }
        }
      `}</style>
    </div>
  );
}