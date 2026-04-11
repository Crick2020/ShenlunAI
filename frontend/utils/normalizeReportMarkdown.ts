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

export function normalizeReportMarkdown(raw: string): string {
  if (!raw || !raw.trim()) return raw;
  const lines = raw.split('\n');
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
      .replace(/如下：\s*\*\*/g, '如下：\n\n**')
      .replace(/。\s*\*\*/g, '。\n\n**')
      .replace(/\*\*\s*>\s+/g, '**\n\n> ')
      .replace(SENTENCE_THEN_QUOTE, '$1\n\n> ');

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
      '$1\n\n$2',
    );
    // 「：1.xxx」且非小数（排除 1.5 这类）
    processed = processed.replace(/([：:])\s*([1-9]\.)(?=[\u4e00-\u9fff])(?!\d)/g, '$1\n\n$2');

    for (const sub of processed.split('\n')) {
      if (sub.length > 0) expanded.push(sub);
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
  return out.join('\n');
}
