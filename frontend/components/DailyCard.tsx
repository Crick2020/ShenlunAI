import React, { useEffect, useState } from 'react';
import type { DailyIndexEntry } from '../types';
import { getFeaturedEntry } from '../services/dailyService';
import { track } from '../services/analytics';

interface DailyCardProps {
  onOpen: (slug: string) => void;
}

function formatDate(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date || '');
  return m ? `${m[1]}年${Number(m[2])}月${Number(m[3])}日` : date;
}

/** 首页「今日精读」卡片：优先今天，当天未上新则回退最新一篇 */
const DailyCard: React.FC<DailyCardProps> = ({ onOpen }) => {
  const [entry, setEntry] = useState<DailyIndexEntry | null>(null);
  const [isToday, setIsToday] = useState(true);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    void getFeaturedEntry()
      .then(({ entry: e, isToday: today }) => {
        if (!alive) return;
        setEntry(e);
        setIsToday(today);
        setLoaded(true);
      })
      .catch(() => {
        if (alive) setLoaded(true);
      });
    return () => { alive = false; };
  }, []);

  if (!loaded) return <div className="daily-card__skeleton" aria-hidden="true" />;
  if (!entry) return null;

  const src = entry.source;
  const open = () => {
    track.dailyOpen(entry.slug);
    onOpen(entry.slug);
  };

  return (
    <section
      className="daily-card"
      role="button"
      tabIndex={0}
      aria-label={`阅读每日精读：${entry.title}`}
      onClick={open}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}
    >
      <div className="daily-card__top">
        <span className="daily-card__eyebrow">
          <i className="daily-card__dot" aria-hidden="true" />
          每日精读 · {formatDate(entry.date)}
        </span>
        <span className="daily-card__flag">{isToday ? '今日上新' : '最新一篇'}</span>
      </div>

      <h2 className="daily-card__title daily-serif">{entry.title}</h2>

      <div className="daily-chips daily-card__chips">
        {entry.keywords.map((k) => <span className="daily-chip" key={k}>{k}</span>)}
      </div>

      <p className="daily-card__summary">{entry.summary}</p>

      <div className="daily-card__meta">
        {src.sourceLabel || `《${src.newspaper || '人民日报'}》`} · {src.page ? `${src.page} · ` : ''}{src.column || '评论'} · 约 {src.charCount} 字
        {entry.edition > 1 ? ` · 第 ${entry.edition} 篇` : ''}
        {entry.structure && entry.structure.hasThesis && entry.structure.hasConclusion && (
          <> · <span className="daily-card__structure">总论点 + {entry.structure.subThesisCount} 个分论点 + 结尾</span></>
        )}
      </div>

      <div className="daily-card__cta">
        <span>开始精读</span>
        <span className="daily-card__arrow"><i className="fas fa-arrow-right" aria-hidden="true" /></span>
      </div>
    </section>
  );
};

export default DailyCard;
