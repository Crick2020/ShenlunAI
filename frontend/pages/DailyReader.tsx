import React, { useEffect, useState } from 'react';
import type { DailyIndexEntry, DailyLecture } from '../types';
import {
  getAllIndex, getDaily, getIndex, getNeighbors, getYearIndex, wasOffline,
} from '../services/dailyService';
import { dailyStaticUrl, openExternalUrl } from '../constants';
import { track } from '../services/analytics';
import DailyDatePicker from '../components/DailyDatePicker';

interface DailyReaderProps {
  slug: string;
  onSelectSlug: (slug: string) => void;
  onBack: () => void;
}

function formatDate(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date || '');
  return m ? `${m[1]} 年 ${Number(m[2])} 月 ${Number(m[3])} 日` : date;
}

function structureStatusLabel(status?: string): string {
  switch (status) {
    case 'standard': return '结构完整 · 可作大作文骨架范本';
    case 'acceptable': return '结构基本完整';
    case 'partial': return '结构待补齐 · 见首段解析';
    default: return '结构参考';
  }
}

function roleClass(role: string): string {
  if (role.startsWith('分论点')) return 'daily-role--sub';
  if (role === '总论点' || role === '结尾') return 'daily-role--key';
  return '';
}

const DailyReader: React.FC<DailyReaderProps> = ({ slug, onSelectSlug, onBack }) => {
  const [lecture, setLecture] = useState<DailyLecture | null>(null);
  const [entries, setEntries] = useState<DailyIndexEntry[]>([]);
  const [neighbors, setNeighbors] = useState<{ prev: DailyIndexEntry | null; next: DailyIndexEntry | null }>({
    prev: null, next: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [allLoaded, setAllLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    void (async () => {
      const [data, list, near] = await Promise.all([getDaily(slug), getIndex(), getNeighbors(slug)]);
      if (!alive) return;
      setLecture(data);
      setEntries(allLoaded ? await getAllIndex() : list);
      setNeighbors(near);
      setError(!data);
      setLoading(false);
      // 瞬时回顶：平滑滚动在用户快速按返回键时会被打断，导致停在中途
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    })();
    return () => { alive = false; };
  }, [slug, allLoaded]);

  // 动态 head：把 SPA 阅读页的权重归并到静态页（唯一权威版本）
  useEffect(() => {
    if (!lecture) return;
    const prevTitle = document.title;
    document.title = `《${lecture.title}》｜申论每日精读 · 爱学申论`;

    const canonical = document.createElement('link');
    canonical.rel = 'canonical';
    canonical.href = dailyStaticUrl(lecture.slug);
    canonical.setAttribute('data-daily-head', '1');
    document.head.appendChild(canonical);

    const desc = document.createElement('meta');
    desc.name = 'description';
    desc.content = lecture.summary;
    desc.setAttribute('data-daily-head', '1');
    document.head.appendChild(desc);

    return () => {
      document.title = prevTitle;
      document.querySelectorAll('[data-daily-head="1"]').forEach((n) => n.remove());
    };
  }, [lecture]);

  const loadAll = async () => {
    const all = await getAllIndex();
    setEntries(all);
    setAllLoaded(true);
  };

  if (loading) {
    return <div className="daily-page"><div className="daily-wrap daily-error">正在加载今日精读…</div></div>;
  }
  if (error || !lecture) {
    return (
      <div className="daily-page">
        <div className="daily-wrap daily-error">
          <p>这篇精读暂时读不到，可能是内容还没发布或网络不通。</p>
          <button type="button" className="daily-nav-btn" onClick={onBack}>返回首页</button>
        </div>
      </div>
    );
  }

  const src = lecture.source;
  const extras = lecture.extras || {} as DailyLecture['extras'];
  const accumulation = extras.accumulation;
  const exercise = extras.exercise;

  return (
    <div className="daily-page">
      <div className="daily-wrap">
        <div className="daily-crumb">
          <a href="/" onClick={(e) => { e.preventDefault(); onBack(); }}>首页</a>
          {' / '}
          <a href="/daily/" onClick={(e) => { e.preventDefault(); openExternalUrl(dailyStaticUrl('index')); }}>每日精读</a>
          {' / '}{lecture.title}
        </div>

        <DailyDatePicker
          entries={entries}
          current={slug}
          onSelect={onSelectSlug}
          onLoadYear={getYearIndex}
          prev={neighbors.prev}
          next={neighbors.next}
          hasMore={!allLoaded}
          allLoaded={allLoaded}
          onLoadAll={loadAll}
        />

        <header className="daily-header">
          <div className="daily-eyebrow"><i className="fas fa-feather-pointed" aria-hidden="true" /> 跟着官媒学申论 · 每日精读</div>
          <h1 className="daily-title daily-serif">{lecture.title}</h1>
          <div className="daily-chips">
            {lecture.keywords.map((k) => <span className="daily-chip daily-chip--blue" key={k}>{k}</span>)}
          </div>
          <div className="daily-meta">
            <span>{src.sourceLabel || `《${src.newspaper}》`} {formatDate(src.paperDate)}</span>
            <span>{src.page}{src.column ? `「${src.column}」` : ''}</span>
            {src.author && <span>作者 {src.author}</span>}
            <span>全文约 {src.charCount} 字</span>
            <span>{lecture.segments.length} 段逐段精讲</span>
            {lecture.edition > 1 && <span>第 {lecture.edition} 篇</span>}
            {src.originalUrl && (
              <a href={src.originalUrl} onClick={(e) => { e.preventDefault(); openExternalUrl(src.originalUrl); }}>
                查看原文 ↗
              </a>
            )}
            {wasOffline() && <span>· 在线内容不可用，正在使用 APP 内置内容</span>}
          </div>
          {lecture.source.structure && (
            <div className="daily-structure">
              <span className="daily-structure__label">申论大作文结构</span>
              <span className={`daily-structure__item ${lecture.source.structure.thesis ? 'is-ok' : ''}`}>总论点</span>
              <span className={`daily-structure__item ${lecture.source.structure.subThesisCount >= 2 ? 'is-ok' : ''}`}>
                {lecture.source.structure.subThesisCount} 个分论点
              </span>
              <span className={`daily-structure__item ${lecture.source.structure.conclusion ? 'is-ok' : ''}`}>结尾回扣</span>
              <span className="daily-structure__status">
                {structureStatusLabel(lecture.source.structure.status)}
                {lecture.source.structure.pattern && lecture.source.structure.pattern !== '无'
                  ? ` · ${lecture.source.structure.pattern}` : ''}
              </span>
            </div>
          )}
          {lecture.source.selectionNote && (
            <div className="daily-selection-note">{lecture.source.selectionNote}</div>
          )}
          <blockquote className="daily-summary">{lecture.summary}</blockquote>
        </header>

        <div className="daily-layout">
          <div className="daily-body">
            {lecture.segments.map((seg) => (
              <section className="daily-segment" id={`seg-${seg.index}`} key={seg.index}>
                <div className="daily-original" id={`orig-${seg.index}`}>
                  <div className="daily-block__head">
                    <span className="daily-badge daily-badge--original">原文 · 第 {seg.index} 段</span>
                    {seg.analysis.structureRole && (
                      <span className={`daily-role ${roleClass(seg.analysis.structureRole)}`}>
                        {seg.analysis.structureRole}
                      </span>
                    )}
                  </div>
                  <div className="daily-block__body" dangerouslySetInnerHTML={{ __html: seg.original.html }} />
                </div>
                <div className="daily-analysis">
                  <div className="daily-block__head">
                    <span className="daily-badge daily-badge--analysis">
                      <i className="fas fa-chalkboard-user" aria-hidden="true" /> 老师解析
                    </span>
                    {seg.analysis.function && <span className="daily-block__fn">{seg.analysis.function}</span>}
                    {seg.analysis.devices?.length > 0 && (
                      <div className="daily-devices">
                        {seg.analysis.devices.slice(0, 3).map((d, i) => (
                          <span className="daily-device" key={`${d}-${i}`}>{d}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="daily-block__body" dangerouslySetInnerHTML={{ __html: seg.analysis.html }} />
                </div>
              </section>
            ))}
          </div>

          <nav className="daily-toc" aria-label="段落导航">
            <span className="daily-toc__title">段落</span>
            {lecture.segments.map((seg) => (
              <a href={`#seg-${seg.index}`} key={seg.index}>{seg.index}</a>
            ))}
          </nav>
        </div>

        <div className="daily-note">
          <strong>【注】</strong> {lecture.note}
        </div>

        <details className="daily-extras">
          <summary>备课加餐 · 框架速览 / 今日积累 / 迁移练习</summary>
          <div className="daily-extras__body">
            {extras.frameworkTable?.length > 0 && (
              <>
                <h4>1. 框架速览（对应四步法第②③步）</h4>
                <table className="daily-table">
                  <thead><tr><th>段落</th><th>结构角色</th><th>功能</th><th>论证方式 / 可借鉴写法</th></tr></thead>
                  <tbody>
                    {extras.frameworkTable.map((r) => (
                      <tr key={r.index}><td>{r.index}</td><td>{r.role || '—'}</td><td>{r.function}</td><td>{r.device}</td></tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {accumulation && (
              <>
                <h4>2. 今日积累清单</h4>
                {accumulation.golden?.length > 0 && (
                  <>
                    <p><strong>金句</strong></p>
                    {accumulation.golden.map((q, i) => <blockquote className="daily-quote" key={i}>{q}</blockquote>)}
                  </>
                )}
                {(['standard', 'templates', 'conceptCards', 'metaphorCards'] as const).map((key) => {
                  const labels: Record<typeof key, string> = {
                    standard: '标准表述', templates: '可套用句式',
                    conceptCards: '概念卡', metaphorCards: '比喻卡',
                  };
                  const list = accumulation[key] || [];
                  if (!list.length) return null;
                  return (
                    <React.Fragment key={key}>
                      <p><strong>{labels[key]}</strong></p>
                      <ul>{list.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </React.Fragment>
                  );
                })}
              </>
            )}

            {exercise && (
              <>
                <h4>3. 迁移练习</h4>
                <div dangerouslySetInnerHTML={{ __html: exercise.html || '' }} />
                {exercise.angles?.length > 0 && (
                  <ul>{exercise.angles.map((a, i) => <li key={i}>{a}</li>)}</ul>
                )}
              </>
            )}
          </div>
        </details>

        {lecture.faq?.length > 0 && (
          <section className="daily-faq">
            <h2 className="daily-section-title">常见问题</h2>
            {lecture.faq.map((f, i) => (
              <details key={i} open={i === 0}>
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </section>
        )}

        <div className="daily-footer-nav">
          <div>
            {neighbors.prev && (
              <button type="button" className="daily-nav-btn" onClick={() => onSelectSlug(neighbors.prev!.slug)}>
                ← 更早：{neighbors.prev.title}
              </button>
            )}
            {neighbors.next && (
              <button type="button" className="daily-nav-btn" onClick={() => onSelectSlug(neighbors.next!.slug)}>
                更新：{neighbors.next.title} →
              </button>
            )}
          </div>
          <div>
            <button type="button" className="daily-nav-btn" onClick={onBack}>返回首页</button>
            {' '}
            <button
              type="button"
              className="daily-nav-btn"
              onClick={() => { track.dailyStaticView(lecture.slug); openExternalUrl(dailyStaticUrl(lecture.slug)); }}
            >
              查看可引用静态版 ↗
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DailyReader;
