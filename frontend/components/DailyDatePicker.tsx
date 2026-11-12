import React, { useEffect, useMemo, useState } from 'react';
import type { DailyIndexEntry } from '../types';
import { track } from '../services/analytics';

interface DailyDatePickerProps {
  entries: DailyIndexEntry[];
  current: string;
  onSelect: (slug: string) => void;
  /** 按需加载某一年全部篇目（读 index-<year>.json），月历切月跨年时使用 */
  onLoadYear?: (year: string) => Promise<DailyIndexEntry[]>;
  prev?: DailyIndexEntry | null;
  next?: DailyIndexEntry | null;
  hasMore?: boolean;
  allLoaded?: boolean;
  onLoadAll?: () => void;
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

const DailyDatePicker: React.FC<DailyDatePickerProps> = ({
  entries, current, onSelect, onLoadYear, prev, next, hasMore, allLoaded, onLoadAll,
}) => {
  const [mode, setMode] = useState<'calendar' | 'strip'>('strip');
  const [yearCache, setYearCache] = useState<Record<string, DailyIndexEntry[]>>({});
  const [viewMonth, setViewMonth] = useState<string>(() => {
    const hit = entries.find((e) => e.slug === current);
    return (hit?.date || entries[0]?.date || new Date().toISOString().slice(0, 10)).slice(0, 7);
  });

  // 合并「近期清单」与「按年加载的清单」，按 slug 去重
  const allEntries = useMemo(() => {
    const map = new Map<string, DailyIndexEntry>();
    for (const list of [...Object.values(yearCache), entries]) {
      for (const e of list) if (!map.has(e.slug)) map.set(e.slug, e);
    }
    return [...map.values()].sort(
      (a, b) => b.date.localeCompare(a.date) || (a.edition || 1) - (b.edition || 1),
    );
  }, [entries, yearCache]);

  const byDate = useMemo(() => {
    const map = new Map<string, DailyIndexEntry[]>();
    for (const e of allEntries) {
      map.set(e.date, [...(map.get(e.date) || []), e]);
    }
    return map;
  }, [allEntries]);

  const currentDate = allEntries.find((e) => e.slug === current)?.date || '';

  // 切月（含跨年）时按需加载该年份清单
  useEffect(() => {
    const year = viewMonth.slice(0, 4);
    if (!onLoadYear || Object.prototype.hasOwnProperty.call(yearCache, year)) return;
    let alive = true;
    void onLoadYear(year).then((list) => {
      if (alive) setYearCache((cache) => ({ ...cache, [year]: list || [] }));
    }).catch(() => {
      if (alive) setYearCache((cache) => ({ ...cache, [year]: [] }));
    });
    return () => { alive = false; };
  }, [viewMonth, onLoadYear, yearCache]);

  const select = (slug: string) => {
    if (!slug || slug === current) return;
    track.dailySwitch(current, slug);
    onSelect(slug);
  };

  const [year, month] = viewMonth.split('-').map(Number);
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const multiDay = currentDate ? (byDate.get(currentDate) || []) : [];

  return (
    <nav className="daily-switcher daily-switcher--stack" aria-label="按日期切换">
      <div className="daily-switcher__top">
        <div className="daily-switcher__heading">
          <div className="daily-switcher__title">按日期切换 · 其他日期的精读</div>
          <div className="daily-switcher__hint">左右横滑选择日期；蓝色为当前篇目</div>
        </div>
        <div className="daily-mode-switch" role="tablist" aria-label="日期浏览方式">
          <button type="button" role="tab" aria-selected={mode === 'calendar'}
            className={`daily-mode-btn ${mode === 'calendar' ? 'is-active' : ''}`}
            onClick={() => setMode('calendar')}>月历</button>
          <button type="button" role="tab" aria-selected={mode === 'strip'}
            className={`daily-mode-btn ${mode === 'strip' ? 'is-active' : ''}`}
            onClick={() => setMode('strip')}>日期条</button>
        </div>
      </div>

      {mode === 'calendar' ? (
        <div className="daily-cal">
          <div className="daily-cal__head">
            <button type="button" className="daily-cal__nav" aria-label="上个月"
              onClick={() => setViewMonth((m) => shiftMonth(m, -1))}>‹</button>
            <strong>{year} 年 {month} 月</strong>
            <button type="button" className="daily-cal__nav" aria-label="下个月"
              onClick={() => setViewMonth((m) => shiftMonth(m, 1))}>›</button>
            <button type="button" className="daily-cal__today"
              onClick={() => {
                const d = currentDate || entries[0]?.date;
                if (d) setViewMonth(d.slice(0, 7));
              }}>回到当前</button>
            <span className="daily-cal__legend">浅蓝=有精读 · 深蓝=当前</span>
          </div>
          <table className="daily-cal__table">
            <thead><tr>{WEEKDAYS.map((w) => <th key={w}>{w}</th>)}</tr></thead>
            <tbody>
              {Array.from({ length: cells.length / 7 }, (_, row) => (
                <tr key={row}>
                  {cells.slice(row * 7, row * 7 + 7).map((day, col) => {
                    if (day === null) return <td key={`e-${row}-${col}`} />;
                    const dateStr = `${year}-${pad(month)}-${pad(day)}`;
                    const list = byDate.get(dateStr) || [];
                    const active = list.some((e) => e.slug === current);
                    return (
                      <td key={dateStr}>
                        <button type="button"
                          className={`daily-cal__day ${list.length ? 'has' : ''} ${active ? 'is-active' : ''}`}
                          disabled={!list.length}
                          title={list.length ? list.map((e) => e.title).join(' / ') : '当日暂无精读'}
                          aria-current={active ? 'date' : undefined}
                          onClick={() => list.length && select(list[0].slug)}>
                          {day}
                          {list.length > 1 && <i className="daily-cal__multi" aria-label="当日多篇" />}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {multiDay.length > 1 && (
            <div className="daily-cal__editions">
              <span>当日共 {multiDay.length} 篇：</span>
              {multiDay.map((e) => (
                <button type="button" key={e.slug}
                  className={`daily-pill ${e.slug === current ? 'daily-pill--active' : ''}`}
                  onClick={() => select(e.slug)}>第 {e.edition || 1} 篇 · {e.title.slice(0, 8)}</button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="daily-switcher__controls">
            <button type="button" className="daily-nav-btn" disabled={!prev}
              onClick={() => prev && select(prev.slug)} aria-label="更早一篇">← 更早</button>
            <button type="button" className="daily-nav-btn" disabled={!next}
              onClick={() => next && select(next.slug)} aria-label="更新一篇">更新 →</button>
            <span className="daily-switcher__range">
              共 {allEntries.length} 篇 · {allEntries[allEntries.length - 1]?.date || ''} ~ {allEntries[0]?.date || ''}
            </span>
          </div>
          <div className="daily-strip">
            {allEntries.map((e) => (
              <button type="button" key={e.slug}
                className={`daily-day-card ${e.slug === current ? 'is-active' : ''}`}
                aria-current={e.slug === current ? 'page' : undefined}
                title={e.title} onClick={() => select(e.slug)}>
                <b>{e.date.slice(5)}{e.edition > 1 ? ` · 第${e.edition}篇` : ''}</b>
                <small>{e.title.slice(0, 9)}…</small>
              </button>
            ))}
            {hasMore && !allLoaded && onLoadAll && (
              <button type="button" className="daily-day-card daily-day-card--more" onClick={onLoadAll}>
                <b>更早 …</b><small>加载全部历史</small>
              </button>
            )}
          </div>
        </>
      )}

      {mode === 'calendar' && (
        <div className="daily-switcher__foot">
          <button type="button" className="daily-nav-btn" disabled={!prev}
            onClick={() => prev && select(prev.slug)} aria-label="更早一篇">← 更早</button>
          <button type="button" className="daily-nav-btn" disabled={!next}
            onClick={() => next && select(next.slug)} aria-label="更新一篇">更新 →</button>
          <span className="daily-switcher__count">共 {allEntries.length} 篇</span>
        </div>
      )}
    </nav>
  );
};

export default DailyDatePicker;
