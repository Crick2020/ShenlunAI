/**
 * 将模型返回的「伪 Markdown」整理为更接近 CommonMark 的文本，便于 react-markdown 正确解析。
 * 典型问题：同一行内写 **...** > 下一段、或引用块内用空格+> 串联多段，导致 > 无法触发行首 blockquote。
 */

const SECTION_AFTER_GT = String.raw`(?:叫好|担忧|因此|此外|然而|但是|总之|综上|首先|其次|再次|最后|其一|其二|其三|一是|二是|三是|建议|结论)`;

/** 仅在「已是引用行」时，按小节词拆分多个 blockquote 行 */
const INLINE_GT_SPLIT = new RegExp(String.raw`\s+>\s+(?=${SECTION_AFTER_GT})`);

/** 句号类标点后接「引用+小节」，常见于模型把总结放在一行内 */
const SENTENCE_THEN_QUOTE = new RegExp(
  String.raw`([\u3002\uff01\uff1f。！？])\s+>\s+(?=(?:因此|总之|综上|但是|然而|此外|建议|结论))`,
  'g',
);

/**
 * CommonMark 的「标点」判定用：ASCII 标点 + 中文标点 + 常见符号。
 * 这里不用 `\p{P}`（Unicode 属性转义需 Chrome 64+，老 WebView 会直接语法报错导致整页白屏）。
 */
const PUNCT_CHARS = new Set<string>([
  '!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/',
  ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`', '{', '|', '}', '~',
  '，', '。', '、', '；', '：', '？', '！', '…', '—', '–', '·', '～', '﹏',
  '「', '」', '『', '』', '《', '》', '〈', '〉', '【', '】', '〔', '〕', '〖', '〗',
  '（', '）', '［', '］', '｛', '｝', '“', '”', '‘', '’', '＂', '＇', '､', '・',
  '•', '◦', '※', '★', '☆', '✓', '✔', '✗', '✘', '⚠', '✅', '❌',
  '➡', '⬅', '⬆', '⬇', '▪', '▫',
]);
const SPACE_CHAR = /\s/;

const isPunct = (ch: string): boolean => !!ch && PUNCT_CHARS.has(ch);

/**
 * CommonMark 判定 `**` 能否开启加粗，用的是「左/右侧标点」规则：
 * 若 `**` 前面紧邻汉字、后面紧邻中文引号等标点，它既不算「左侧合法」也不算右侧合法，
 * 解析器会把 ** 当普通字符，页面上就直接显示 `**材料…**`。
 * 例：`核心原词是**“农村职业经理人”**` → 不会加粗；`核心原词是“**农村职业经理人**”` → 正常加粗。
 * 这里把夹在 `**` 与正文之间的首尾标点挪到 `**` 外侧，视觉一致，但解析器能认。
 */
function hoistEdgePunctuation(text: string): string {
  return text.replace(
    /\*\*([^\n]+?)\*\*/g,
    (match: string, inner: string, offset: number, whole: string) => {
      let core = inner;
      const prev = offset > 0 ? whole[offset - 1] : '';
      const next = offset + match.length < whole.length ? whole[offset + match.length] : '';
      const openingBlocked =
        !!prev && !SPACE_CHAR.test(prev) && !isPunct(prev) && isPunct(core[0]);
      const closingBlocked =
        !!next && !SPACE_CHAR.test(next) && !isPunct(next) && isPunct(core[core.length - 1]);
      if (!openingBlocked && !closingBlocked) return match;

      // 只要有一侧不成立，就对称地把首尾标点一起挪到 ** 外侧，避免引号一半在粗体内一半在外
      let lead = '';
      let trail = '';
      while (core.length > 1 && isPunct(core[0])) {
        lead += core[0];
        core = core.slice(1);
      }
      while (core.length > 1 && isPunct(core[core.length - 1])) {
        trail = core[core.length - 1] + trail;
        core = core.slice(0, -1);
      }
      if (!core.trim()) return match;
      return `${lead}**${core}**${trail}`;
    },
  );
}

/** 行内代码（`...`）里的 ** 不能动，按反引号切片后只处理非代码段 */
function fixEmphasisFlanking(line: string): string {
  if (!line.includes('**')) return line;
  return line
    .split(/(`[^`]*`)/)
    .map((part) => (part.startsWith('`') && part.endsWith('`') ? part : hoistEdgePunctuation(part)))
    .join('');
}

export function normalizeReportMarkdown(raw: string): string {
  if (!raw || !raw.trim()) return raw;
  // 模型偶发把 Markdown 标记转义成 \*\*...\*\*，会导致页面显示字面量 **。
  // 先做轻量“反转义”，仅处理常见格式标记，避免误改正文中的反斜杠。
  const preprocessed = raw
    .replace(/\\\*\\\*/g, '**')
    .replace(/\\`/g, '`')
    .replace(/\\#/g, '#')
    .replace(/\\>/g, '>');

  const lines = preprocessed.split('\n');
  let inCodeBlock = false;
  const expanded: string[] = [];

  for (const line of lines) {
    if (line.trimStart().startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      expanded.push(line);
      continue;
    }
    if (inCodeBlock) {
      expanded.push(line);
      continue;
    }

    let processed = line
      .replace(/如下：\s*\*\*/g, '如下：\n**')
      .replace(/。\s*\*\*/g, '。\n**')
      .replace(/\*\*\s*>\s+/g, '**\n> ')
      .replace(SENTENCE_THEN_QUOTE, '$1\n> ');

    if (/^\s*>/.test(processed) && INLINE_GT_SPLIT.test(processed)) {
      const parts = processed.split(INLINE_GT_SPLIT);
      processed = parts
        .map((p) => {
          const inner = p.trim().replace(/^>\s*/, '');
          return inner ? `> ${inner}` : '';
        })
        .filter(Boolean)
        .join('\n');
    }

    // 长句里「1. 2. 3.」挤在一行时，拆成多行以便渲染为有序列表（2. 起且前接句号/分号）
    processed = processed.replace(
      /([\u3002\uff01\uff1f；。！？;])\s*([2-9]\.)(?=[\u4e00-\u9fff])/g,
      '$1\n$2',
    );
    // 兜底：2. 后面若是符号/emoji（如 ⚠️）而非中文，也要断行
    processed = processed.replace(
      /([\u3002\uff01\uff1f；。！？;])\s*([2-9]\.)(?=\S)/g,
      '$1\n$2',
    );
    // 「：1.xxx」且非小数（排除 1.5 这类）
    processed = processed.replace(/([：:])\s*([1-9]\.)(?=[\u4e00-\u9fff])(?!\d)/g, '$1\n$2');
    // 兜底：如「...） 2.材料...」这种前面不是句号也要断行
    processed = processed.replace(/(\S)\s+([2-9]\.)(?=[\u4e00-\u9fff])(?!\d)/g, '$1\n$2');

    // 保留模型输出的空行：公文「标题 / 主送 / 正文 / 落款 / 日期」靠空行分段，
    // 丢掉空行会把整篇公文压成一个 <p>。自动断行的结果只是软换行，不制造新段落。
    for (const sub of processed.split('\n')) {
      if (sub.length === 0) {
        // 连续空行压缩为一个，避免报告出现大片空白
        if (expanded.length > 0 && expanded[expanded.length - 1] !== '') expanded.push('');
        continue;
      }
      expanded.push(fixEmphasisFlanking(sub));
    }
  }

  let inCode = false;
  const out: string[] = [];
  for (const line of expanded) {
    if (line.trimStart().startsWith('```')) inCode = !inCode;
    if (!inCode && line.includes('**')) {
      const count = (line.match(/\*\*/g) || []).length;
      if (count % 2 === 1) out.push(`${line}**`);
      else out.push(line);
    } else {
      out.push(line);
    }
  }
  // 去掉首尾多余空行，但保留行首缩进（列表/引用需要）
  return out.join('\n').replace(/^\n+|\n+$/g, '');
}

/**
 * 复制 Markdown 时，避免被部分编辑器误判为 Setext 二级标题：
 * 若出现「正文行 + 下一行 ---/===」，在分隔线前补一个空行，强制其作为分割线而非标题下划线。
 */
export function normalizeReportMarkdownForCopy(raw: string): string {
  const normalized = normalizeReportMarkdown(raw);
  if (!normalized) return normalized;

  const lines = normalized.split('\n');
  const out: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const isSetextUnderline = /^\s*(?:-{3,}|={3,})\s*$/.test(line);
    if (isSetextUnderline && out.length > 0) {
      const prev = out[out.length - 1];
      if (prev.trim() !== '') out.push('');
    }
    out.push(line);
  }

  return out.join('\n');
}

/** 行首「枚举序号」改为全角句点，避免 Word/飞书 把 `1.` 识别为有序列表层级 */
function lineLeadingEnumToFullwidthDot(line: string): string {
  return line.replace(
    /^(\s*)(\d+)\.(?=\s|[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefA-Za-z「“])/,
    '$1$2．',
  );
}

/** 去掉行首无序列表标记，保留缩进，避免嵌套项（如 * 点评）与上级对齐后像独立小标题 */
function stripLeadingUnorderedBullet(line: string): string {
  const withSpace = line.replace(/^(\s*)[-*+]\s+/, '$1');
  if (withSpace !== line) return withSpace;
  // 模型偶发 `*点评：` 无空格
  return line.replace(/^(\s*)\*(?=[\u4e00-\u9fff「“『])/u, '$1');
}

/** 去掉行首引用符，保留缩进 */
function stripLeadingBlockquote(line: string): string {
  return line.replace(/^(\s*)>\s?/, '$1');
}

/**
 * 将 Markdown 转为适合「复制到 Word / 飞书 / Notion」的纯文本：去掉 #、**、列表符等，
 * 且保留行首空格缩进，使「* 点评」等仍显示在「3.」要点之下。
 */
export function reportMarkdownToPlainText(markdown: string): string {
  if (!markdown || !markdown.trim()) return '';

  let s = markdown.replace(/```[\w-]*\s*\n([\s\S]*?)```/g, (_, inner: string) => `\n${inner.trim()}\n`);

  const lines = s.split('\n');
  const outLines: string[] = [];
  for (const raw of lines) {
    let line = raw;
    const atx = /^\s{0,3}#{1,6}\s+(.*)$/.exec(line);
    if (atx) {
      line = atx[1].trimEnd();
    }
    line = stripLeadingBlockquote(line);
    line = stripLeadingUnorderedBullet(line);
    line = lineLeadingEnumToFullwidthDot(line);
    if (/^\s*(=+|-+)\s*$/.test(line)) {
      continue;
    }
    if (/^\s*([-*_]\s*){3,}\s*$/.test(line)) {
      outLines.push('');
      continue;
    }
    outLines.push(line);
  }
  s = outLines.join('\n');

  let prev = '';
  while (prev !== s) {
    prev = s;
    s = s.replace(/\*\*([^*]+)\*\*/g, '$1');
  }
  s = s.replace(/`([^`]+)`/g, '$1');
  s = s.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1');
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  s = s.replace(/\*([^*\n]+)\*/g, '$1');
  s = s.replace(/~~([^~]+)~~/g, '$1');

  s = s
    .split('\n')
    .map((row) => {
      if (/^\s*\|.*\|\s*$/.test(row) && (row.match(/\|/g) || []).length >= 2) {
        return row
          .trim()
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((c) => c.trim())
          .join('　');
      }
      return row;
    })
    .join('\n');

  s = s
    .split('\n')
    .map((row) => lineLeadingEnumToFullwidthDot(row))
    .join('\n');

  s = s.replace(/\n{3,}/g, '\n\n').trim();
  return s;
}
