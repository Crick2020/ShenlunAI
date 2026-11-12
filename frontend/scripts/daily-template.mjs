/**
 * 每日精读静态 HTML / Markdown 模板。
 * 生成的 HTML 完全不依赖 JS，view-source 即可读到全部正文与结构化数据。
 */
import {
  SITE_URL, articleUrl, markdownUrl, spaUrl, escapeHtml, safeRichHtml,
  htmlToMarkdown, formatDateCN, jsonLd, truncate, isoDate,
} from './daily-shared.mjs';

function structureStatusLabel(status) {
  switch (status) {
    case 'standard': return '结构完整 · 可作大作文骨架范本';
    case 'acceptable': return '结构基本完整';
    case 'partial': return '结构待补齐 · 见首段解析';
    default: return '结构参考';
  }
}

function roleClass(role) {
  if (String(role).startsWith('分论点')) return 'daily-role--sub';
  if (role === '总论点' || role === '结尾') return 'daily-role--key';
  return '';
}

function head(doc) {
  const canonical = articleUrl(doc.slug);
  const src = doc.source || {};
  const title = `《${doc.title}》｜申论每日精读 · 爱学申论`;
  const description = truncate(doc.summary || '', 155);
  const published = doc.generatedAt || `${doc.date}T08:20:00+08:00`;

  const articleLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: `《${doc.title}》申论每日精读：原文与老师逐段解析`,
    description: doc.summary,
    datePublished: published,
    dateModified: published,
    author: { '@type': 'Person', name: '爱学申论教研老师' },
    publisher: { '@type': 'Organization', name: '爱学申论', url: SITE_URL },
    mainEntityOfPage: { '@type': 'WebPage', '@id': canonical },
    inLanguage: 'zh-CN',
    keywords: (doc.keywords || []).join('、'),
    wordCount: src.charCount || 0,
    articleSection: src.column || '申论范文',
    isBasedOn: src.originalUrl || undefined,
    citation: src.originalUrl ? {
      '@type': 'CreativeWork',
      name: src.originalTitle || doc.title,
      url: src.originalUrl,
      publisher: { '@type': 'Organization', name: src.newspaper || '人民日报' },
    } : undefined,
    about: (doc.keywords || []).map((k) => ({ '@type': 'Thing', name: k })),
  };
  const breadcrumbLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: '首页', item: `${SITE_URL}/` },
      { '@type': 'ListItem', position: 2, name: '每日精读', item: `${SITE_URL}/daily/` },
      { '@type': 'ListItem', position: 3, name: doc.title, item: canonical },
    ],
  };
  const faqLd = (doc.faq || []).length ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: doc.faq.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  } : null;

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<meta name="keywords" content="${escapeHtml([doc.title, ...(doc.keywords || []), '申论范文', '申论素材', '申论每日精读'].join(', '))}">
<meta name="author" content="爱学申论">
<link rel="canonical" href="${escapeHtml(canonical)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="爱学申论">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="${escapeHtml(title)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${escapeHtml(canonical)}">
<meta property="article:published_time" content="${escapeHtml(published)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(title)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<link rel="alternate" type="text/markdown" href="${escapeHtml(markdownUrl(doc.slug))}" title="纯文本版">
<link rel="alternate" type="application/rss+xml" href="${SITE_URL}/rss.xml" title="申论每日精读">
<script type="application/ld+json">${jsonLd(articleLd)}</script>
<script type="application/ld+json">${jsonLd(breadcrumbLd)}</script>
${faqLd ? `<script type="application/ld+json">${jsonLd(faqLd)}</script>` : ''}
<style>
${'__DAILY_CSS__'}
</style>
</head>`;
}

function siteHeader() {
  return `<header class="daily-site-header">
  <div class="daily-site-header__inner">
    <a class="daily-brand" href="${SITE_URL}/"><span class="daily-brand__mark">✒</span>爱学申论</a>
    <nav class="daily-site-nav">
      <a href="${SITE_URL}/">题库批改</a>
      <a href="${SITE_URL}/daily/">每日精读</a>
      <a href="${SITE_URL}/rss.xml">RSS</a>
    </nav>
  </div>
</header>`;
}

function siteFooter() {
  return `<footer class="daily-site-footer">
  <p>爱学申论 · 跟着官媒学申论。原文版权归原刊及作者所有，讲义仅供学习交流使用。</p>
  <p>
    <a href="${SITE_URL}/daily/">精读归档</a>
    <a href="${SITE_URL}/sitemap.xml">Sitemap</a>
    <a href="${SITE_URL}/rss.xml">RSS</a>
    <a href="${SITE_URL}/llms.txt">llms.txt</a>
    <a href="${SITE_URL}/">返回首页</a>
  </p>
</footer>`;
}

function renderSegments(doc) {
  return doc.segments.map((seg) => {
    const devices = (seg.analysis.devices || []).slice(0, 3)
      .map((d) => `<span class="daily-device">${escapeHtml(d)}</span>`).join('');
    return `<section class="daily-segment" id="seg-${seg.index}">
  <div class="daily-original" id="orig-${seg.index}">
    <div class="daily-block__head">
      <span class="daily-badge daily-badge--original">原文 · 第 ${seg.index} 段</span>
      ${seg.analysis.structureRole ? `<span class="daily-role ${roleClass(seg.analysis.structureRole)}">${escapeHtml(seg.analysis.structureRole)}</span>` : ''}
    </div>
    <div class="daily-block__body">${safeRichHtml(seg.original.html)}</div>
  </div>
  <div class="daily-analysis">
    <div class="daily-block__head">
      <span class="daily-badge daily-badge--analysis">✎ 老师解析</span>
      ${seg.analysis.function ? `<span class="daily-block__fn">${escapeHtml(seg.analysis.function)}</span>` : ''}
      ${devices ? `<div class="daily-devices">${devices}</div>` : ''}
    </div>
    <div class="daily-block__body">${safeRichHtml(seg.analysis.html)}</div>
  </div>
</section>`;
  }).join('\n');
}

function renderExtras(doc) {
  const extras = doc.extras || {};
  const acc = extras.accumulation || {};
  const blocks = [];

  if ((extras.frameworkTable || []).length) {
    const rows = extras.frameworkTable.map((r) =>
      `<tr><td>${r.index}</td><td>${escapeHtml(r.role || '—')}</td><td>${escapeHtml(r.function)}</td><td>${escapeHtml(r.device)}</td></tr>`).join('');
    blocks.push(`<h4>1. 框架速览（结构角色 / 段落功能 / 论证方式）</h4>
<table class="daily-table"><thead><tr><th>段落</th><th>结构角色</th><th>功能</th><th>论证方式 / 可借鉴写法</th></tr></thead><tbody>${rows}</tbody></table>`);
  }

  const lists = [
    ['golden', '金句'], ['standard', '标准表述'], ['templates', '可套用句式'],
    ['conceptCards', '概念卡'], ['metaphorCards', '比喻卡'],
  ];
  const accHtml = [];
  for (const [key, label] of lists) {
    const items = acc[key] || [];
    if (!items.length) continue;
    accHtml.push(`<p><strong>${label}</strong></p>`);
    if (key === 'golden') {
      accHtml.push(items.map((q) => `<blockquote class="daily-quote">${escapeHtml(q)}</blockquote>`).join(''));
    } else {
      accHtml.push(`<ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`);
    }
  }
  if (accHtml.length) blocks.push(`<h4>2. 今日积累清单</h4>${accHtml.join('')}`);

  const exercise = extras.exercise || {};
  if (exercise.html || (exercise.angles || []).length) {
    blocks.push(`<h4>3. 迁移练习</h4>${safeRichHtml(exercise.html || '')}
<ul>${(exercise.angles || []).map((a) => `<li>${escapeHtml(a)}</li>`).join('')}</ul>`);
  }

  if (!blocks.length) return '';
  return `<details class="daily-extras">
  <summary>备课加餐 · 框架速览 / 今日积累 / 迁移练习</summary>
  <div class="daily-extras__body">${blocks.join('\n')}</div>
</details>`;
}

function renderFaq(doc) {
  if (!(doc.faq || []).length) return '';
  return `<section class="daily-faq">
  <h2 class="daily-section-title">常见问题</h2>
  ${doc.faq.map((f, i) => `<details ${i === 0 ? 'open' : ''}><summary>${escapeHtml(f.q)}</summary><p>${escapeHtml(f.a)}</p></details>`).join('\n')}
</section>`;
}

export function renderArticleHtml(doc, ctx = {}) {
  const src = doc.source || {};
  const prev = ctx.prev || null;
  const next = ctx.next || null;

  const keywordsDl = `<dl class="daily-chips">
    <dt class="daily-toc__title">关键词</dt>
    ${(doc.keywords || []).map((k) => `<dd class="daily-chip daily-chip--blue">${escapeHtml(k)}</dd>`).join('')}
  </dl>`;

  const st = (doc.source || {}).structure;
  const structureHtml = st ? `<div class="daily-structure">
    <span class="daily-structure__label">申论大作文结构</span>
    <span class="daily-structure__item${st.thesis ? ' is-ok' : ''}">总论点</span>
    <span class="daily-structure__item${st.subThesisCount >= 2 ? ' is-ok' : ''}">${st.subThesisCount} 个分论点</span>
    <span class="daily-structure__item${st.conclusion ? ' is-ok' : ''}">结尾回扣</span>
    <span class="daily-structure__status">${escapeHtml(structureStatusLabel(st.status))}${st.pattern && st.pattern !== '无' ? ' · ' + escapeHtml(st.pattern) : ''}${st.strict && st.strict.pass ? ' · 严格分论点' : ''}</span>
  </div>`
    + (st && st.strict && st.strict.pass
      ? `<p class="daily-structure-note">本文经申论大作文结构校验：总论点明确，含 ${st.subThesisCount} 个相互独立、段内展开论证的分论点，并以结尾收束回扣，可直接作为考场大作文的骨架范本。</p>`
      : '') : '';

  const selectionNoteHtml = (doc.source || {}).selectionNote
    ? `<div class="daily-selection-note">${escapeHtml(doc.source.selectionNote)}</div>` : '';

  return `${head(doc)}
<body class="daily-page">
${siteHeader()}
<main class="daily-wrap">
  <nav class="daily-crumb"><a href="${SITE_URL}/">首页</a> / <a href="${SITE_URL}/daily/">每日精读</a> / ${escapeHtml(doc.title)}</nav>

  <article>
    <header class="daily-header">
      <div class="daily-eyebrow">跟着官媒学申论 · 每日精读</div>
      <h1 class="daily-title daily-serif">${escapeHtml(doc.title)}</h1>
      ${keywordsDl}
      ${structureHtml}
      ${selectionNoteHtml}
      <div class="daily-meta">
        <span>${escapeHtml(src.sourceLabel || `《${src.newspaper || '人民日报'}》`)} <time datetime="${escapeHtml(src.paperDate || doc.date)}">${formatDateCN(src.paperDate || doc.date)}</time></span>
        <span>${escapeHtml(src.page || '')}${src.column ? `「${escapeHtml(src.column)}」` : ''}</span>
        ${src.author ? `<span>作者 ${escapeHtml(src.author)}</span>` : ''}
        <span>全文约 ${src.charCount || 0} 字</span>
        <span>${doc.segments.length} 段逐段精讲</span>
        ${src.originalUrl ? `<a href="${escapeHtml(src.originalUrl)}" rel="noopener noreferrer" target="_blank">查看原文 ↗</a>` : ''}
      </div>
      <blockquote class="daily-summary">${escapeHtml(doc.summary)}</blockquote>
    </header>

    <div class="daily-layout">
      <div class="daily-body">
${renderSegments(doc)}
      </div>
      <nav class="daily-toc" aria-label="段落导航">
        <span class="daily-toc__title">段落</span>
        ${doc.segments.map((s) => `<a href="#seg-${s.index}">${s.index}</a>`).join('')}
      </nav>
    </div>

    <div class="daily-note"><strong>【注】</strong> ${escapeHtml(doc.note)}</div>

${renderExtras(doc)}
${renderFaq(doc)}

    <footer class="daily-footer-nav">
      <div>
        ${prev ? `<a class="daily-nav-btn" href="${escapeHtml(articleUrl(prev.slug))}">← 更早：${escapeHtml(prev.title)}</a>` : ''}
        ${next ? `<a class="daily-nav-btn" href="${escapeHtml(articleUrl(next.slug))}">更新：${escapeHtml(next.title)} →</a>` : ''}
      </div>
      <div>
        <a class="daily-nav-btn" href="${SITE_URL}/daily/">全部精读</a>
        <a class="daily-cta" href="${escapeHtml(spaUrl(doc.slug))}">在 APP / 网站内阅读 →</a>
      </div>
    </footer>
  </article>
</main>
${siteFooter()}
</body>
</html>
`;
}

/** 纯 Markdown 版：给大模型 / 阅读器直接抓取，无 HTML 噪声 */
export function renderArticleMarkdown(doc) {
  const src = doc.source || {};
  const lines = [
    `# 《${doc.title}》｜申论每日精读`,
    '',
    `- 来源：${src.sourceLabel || `《${src.newspaper || '人民日报'}》`}${src.paperDate || doc.date} ${src.page || ''}${src.column ? `「${src.column}」` : ''}`,
    `- 作者：${src.author || '未署名'}`,
    `- 原题：${src.originalTitle || doc.title}`,
    `- 原文链接：${src.originalUrl || '见原刊网站'}`,
    `- 全文约 ${src.charCount || 0} 字，共 ${doc.segments.length} 段`,
    `- 关键词：${(doc.keywords || []).join('；')}`,
    `- 永久链接：${articleUrl(doc.slug)}`,
    '',
    `> ${doc.summary}`,
    '',
    '## 原文与老师逐段解析',
    '',
  ];

  if ((doc.source || {}).selectionNote) {
    lines.push(`> 选文说明：${doc.source.selectionNote}`, '');
  }

  const st = (doc.source || {}).structure;
  if (st) {
    lines.push('## 申论大作文结构骨架', '',
      `- 总论点：${st.thesis ? `第 ${st.thesis.paragraph} 段，${st.thesis.sentence}` : '未识别'}`,
      `- 分论点：${st.subThesisCount} 个${(st.subTheses || []).length ? '（' + st.subTheses.map((s) => `第 ${s.paragraph} 段`).join('、') + '）' : ''}`,
      `- 结尾：${st.conclusion ? `第 ${st.conclusion.paragraph} 段${st.conclusion.titleEcho ? '，回扣标题' : ''}` : '未识别'}`,
      `- 结构判定：${st.status}（${st.score}/100，逐段角色：${(st.outline || []).map((r, i) => `第${i + 1}段 ${r}`).join('；')}）`,
      `- 结构关系：${st.pattern || '无'}；严格分论点判定：${st.strict && st.strict.pass ? '通过' : '未通过'}`,
      `- 分论点位置：${(st.subTheses || []).map((s) => `第 ${s.paragraph} 段`).join('、') || '未识别'}，各段段首均为可独立成立的主张句且段内展开论证`,
      '');
  }

  for (const seg of doc.segments) {
    lines.push(`### 第 ${seg.index} 段（${seg.analysis.structureRole || '段落'}）`, '', '**【原文】**', '', htmlToMarkdown(seg.original.html), '',
      `**【老师解析】**（${seg.analysis.function || '段落解析'}）`, '',
      htmlToMarkdown(seg.analysis.html), '');
    if ((seg.analysis.quotes || []).length) {
      lines.push(`本段金句：${seg.analysis.quotes.map((q) => `「${q}」`).join('、')}`, '');
    }
  }

  const extras = doc.extras || {};
  if ((extras.frameworkTable || []).length) {
    lines.push('## 框架速览', '', '| 段落 | 结构角色 | 功能 | 论证方式 |', '| --- | --- | --- | --- |');
    for (const r of extras.frameworkTable) {
      lines.push(`| ${r.index} | ${r.role || '—'} | ${r.function} | ${r.device} |`);
    }
    lines.push('');
  }
  const acc = extras.accumulation || {};
  for (const [key, label] of [['golden', '金句'], ['standard', '标准表述'], ['templates', '可套用句式'], ['conceptCards', '概念卡'], ['metaphorCards', '比喻卡']]) {
    if ((acc[key] || []).length) lines.push(`## ${label}`, '', ...acc[key].map((x) => `- ${x}`), '');
  }
  if (extras.exercise) {
    lines.push('## 迁移练习', '', htmlToMarkdown(extras.exercise.html || ''), '',
      ...(extras.exercise.angles || []).map((a) => `- ${a}`), '');
  }
  if ((doc.faq || []).length) {
    lines.push('## 常见问题', '');
    for (const f of doc.faq) lines.push(`**Q：${f.q}**`, '', `A：${f.a}`, '');
  }
  lines.push('---', '', `【注】${doc.note}`, '', `本页由爱学申论自动生成，永久链接：${articleUrl(doc.slug)}`);
  return lines.join('\n') + '\n';
}

/** 归档总览页 */
export function renderArchiveHtml(entries, years) {
  const recent = entries.slice(0, 20);
  const itemListLd = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: '申论每日精读归档',
    numberOfItems: entries.length,
    itemListElement: entries.slice(0, 50).map((e, i) => ({
      '@type': 'ListItem', position: i + 1,
      name: e.title, url: articleUrl(e.slug),
    })),
  };
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>申论每日精读归档 · 爱学申论</title>
<meta name="description" content="每天从人民日报、人民网、人民论坛网、光明网、中国经济网、共产党员网等官媒选一篇申论大作文范文逐段精讲：总论点 + 严格分论点 + 结尾，原文 + 老师解析，按日期归档，共 ${entries.length} 篇。">
<link rel="canonical" href="${SITE_URL}/daily/">
<meta property="og:title" content="申论每日精读归档 · 爱学申论">
<meta property="og:url" content="${SITE_URL}/daily/">
<link rel="alternate" type="application/rss+xml" href="${SITE_URL}/rss.xml" title="申论每日精读">
<script type="application/ld+json">${jsonLd(itemListLd)}</script>
<style>
${'__DAILY_CSS__'}
</style>
</head>
<body class="daily-page">
${siteHeader()}
<main class="daily-wrap">
  <nav class="daily-crumb"><a href="${SITE_URL}/">首页</a> / 每日精读</nav>
  <div class="daily-eyebrow">跟着官媒学申论</div>
  <h1 class="daily-title daily-serif">申论每日精读归档</h1>
  <blockquote class="daily-summary">每天从人民日报、人民网、人民论坛网、光明网、中国经济网、共产党员网等官媒评论栏目，选一篇具备「明确总论点 + 若干严格分论点 + 结尾」的申论大作文范文，产出「原文 + 老师逐段解析」讲义：拆段落功能、论证方式、金句标准表述、举一反三例句与迁移练习。共 ${entries.length} 篇，原文均回链原刊，仅供学习交流。</blockquote>

  <h2 class="daily-section-title">按年份浏览</h2>
  <div class="daily-related">${years.map((y) => `<a href="${SITE_URL}/daily/archive/${y}.html">${y} 年 →</a>`).join('')}</div>

  <h2 class="daily-section-title">最近更新</h2>
  <div class="daily-archive-group">
    <ul class="daily-archive-list">${recent.map((e) => `<li>
      <time datetime="${escapeHtml(e.date)}">${escapeHtml(e.date)}</time>
      <a href="${escapeHtml(articleUrl(e.slug))}">${escapeHtml(e.title)}</a>
      <span class="daily-chip">${escapeHtml(e.source?.column || '评论')}</span>
      <span class="daily-chip">${escapeHtml((e.keywords || []).slice(0, 2).join(' / '))}</span>
    </li>`).join('')}</ul>
  </div>
  ${years.map((y) => `<p><a href="${SITE_URL}/daily/archive/${y}.html">查看 ${y} 年全部精读 →</a></p>`).join('')}
</main>
${siteFooter()}
</body>
</html>
`;
}

/** 按日期快速跳转的横向日期条（纯 HTML，不依赖 JS，与阅读页切换器一致） */
function dateStripHtml(entries) {
  return `<div class="daily-strip">${entries.map((e) => `
    <a class="daily-day-card" href="${escapeHtml(articleUrl(e.slug))}" title="${escapeHtml(e.title)}">
      <b>${escapeHtml(e.date.slice(5))}${e.edition > 1 ? ` · 第${e.edition}篇` : ''}</b>
      <small>${escapeHtml(e.title.slice(0, 9))}…</small>
    </a>`).join('')}</div>`;
}

/** 按年归档页 */
export function renderYearArchiveHtml(year, entries) {
  const dateStrip = dateStripHtml(entries);
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${year} 年申论每日精读归档 · 爱学申论</title>
<meta name="description" content="${year} 年申论每日精读全部 ${entries.length} 篇，官媒申论大作文范文逐段精讲。">
<link rel="canonical" href="${SITE_URL}/daily/archive/${year}.html">
<style>
${'__DAILY_CSS__'}
</style>
</head>
<body class="daily-page">
${siteHeader()}
<main class="daily-wrap">
  <nav class="daily-crumb"><a href="${SITE_URL}/">首页</a> / <a href="${SITE_URL}/daily/">每日精读</a> / ${year} 年</nav>
  <h1 class="daily-title daily-serif">${year} 年申论每日精读</h1>
  <p class="daily-muted">共 ${entries.length} 篇，按日期倒序。可左右横滑快速跳转到其他日期。</p>
  <section class="daily-mini-cal__wrap">
    <h2 class="daily-section-title">按日期快速跳转</h2>
    ${dateStrip}
  </section>
  <div class="daily-archive-group">
    <ul class="daily-archive-list">${entries.map((e) => `<li>
      <time datetime="${escapeHtml(e.date)}">${escapeHtml(e.date)}</time>
      <a href="${escapeHtml(articleUrl(e.slug))}">${escapeHtml(e.title)}</a>
      <span class="daily-chip">${escapeHtml(e.source?.column || '评论')}</span>
      <span class="daily-chip">${escapeHtml((e.keywords || []).slice(0, 3).join(' / '))}</span>
    </li>`).join('')}</ul>
  </div>
  <p><a href="${SITE_URL}/daily/">← 返回全部归档</a></p>
</main>
${siteFooter()}
</body>
</html>
`;
}
