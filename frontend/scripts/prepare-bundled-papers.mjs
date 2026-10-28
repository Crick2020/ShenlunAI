import { access, copyFile, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceCandidates = [
  path.resolve(projectRoot, '..', 'backend', 'data'),
  path.resolve(projectRoot, 'backend', 'data'),
];
const outputDir = path.resolve(projectRoot, 'public', 'papers');

async function findSourceDir() {
  for (const candidate of sourceCandidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Try the next repository layout.
    }
  }
  throw new Error('Cannot find backend/data. Run this command from the full ShenlunAI repository.');
}

const sourceDir = await findSourceDir();
const entries = await readdir(sourceDir, { withFileTypes: true });
const papers = [];

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });

for (const entry of entries) {
  if (!entry.isFile() || !entry.name.endsWith('.json')) continue;

  const sourcePath = path.join(sourceDir, entry.name);
  try {
    const paper = JSON.parse(await readFile(sourcePath, 'utf8'));
    const id = String(paper.id || entry.name.slice(0, -5));
    papers.push({
      id,
      name: paper.name || '未命名试卷',
      year: paper.year || 2024,
      region: paper.region || '全国',
      examType: paper.examType || '公务员',
    });
    await copyFile(sourcePath, path.join(outputDir, `${id}.json`));
  } catch (error) {
    console.warn(`[papers] skipped ${entry.name}: ${error.message}`);
  }
}

papers.sort((a, b) => {
  const nationalA = a.region === '全国' ? 0 : 1;
  const nationalB = b.region === '全国' ? 0 : 1;
  return nationalA - nationalB
    || String(a.region).localeCompare(String(b.region), 'zh-CN')
    || Number(b.year) - Number(a.year);
});

await writeFile(path.join(outputDir, 'index.json'), JSON.stringify(papers), 'utf8');
console.log(`[papers] bundled ${papers.length} papers into public/papers`);
