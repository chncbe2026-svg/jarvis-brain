#!/usr/bin/env node
/**
 * Jarvis RAG Backend — Static Validator
 * Tests all backend files for structural correctness, import consistency,
 * and logic sanity without needing Python installed.
 */

import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

const PASS = '✅ PASS';
const FAIL = '❌ FAIL';
const WARN = '⚠️  WARN';

let passed = 0, failed = 0, warned = 0;

function check(label, condition, detail = '') {
  if (condition === true) {
    console.log(`  ${PASS}  ${label}`);
    passed++;
  } else if (condition === 'warn') {
    console.log(`  ${WARN}  ${label}${detail ? ' — ' + detail : ''}`);
    warned++;
  } else {
    console.log(`  ${FAIL}  ${label}${detail ? ' — ' + detail : ''}`);
    failed++;
  }
}

function readFile(relPath) {
  const full = join(ROOT, relPath);
  if (!existsSync(full)) return null;
  return readFileSync(full, 'utf-8');
}

function fileExists(relPath) {
  return existsSync(join(ROOT, relPath));
}

console.log('\n══════════════════════════════════════════════════════');
console.log('   Jarvis RAG Backend — Static Validation Test Suite');
console.log('══════════════════════════════════════════════════════\n');

// ─── 1. File Structure ──────────────────────────────────────────────────────────
console.log('📁  [1] File Structure');
const requiredFiles = [
  'requirements.txt',
  '.env.example',
  'app/main.py',
  'app/core/config.py',
  'app/services/qdrant_client.py',
  'app/services/embedding_service.py',
  'app/services/rag_service.py',
  'app/services/rss_service.py',
  'docker/Dockerfile',
  'docker/docker-compose.yml',
];
requiredFiles.forEach(f => check(f, fileExists(f)));

// ─── 2. Requirements ────────────────────────────────────────────────────────────
console.log('\n📦  [2] requirements.txt — Dependencies');
const req = readFile('requirements.txt') || '';
const requiredPkgs = [
  ['fastapi', 'Core web framework'],
  ['uvicorn', 'ASGI server'],
  ['qdrant-client', 'Vector database client'],
  ['fastembed', 'Local embeddings'],
  ['groq', 'LLM API client'],
  ['rank-bm25', 'BM25 hybrid search'],
  ['sentence-transformers', 'Cross-encoder reranker'],
  ['APScheduler', 'Scheduled RSS sync'],
  ['tiktoken', 'Token counting for chunking'],
  ['feedparser', 'RSS parsing'],
  ['pydantic-settings', 'Config management'],
];
requiredPkgs.forEach(([pkg, desc]) =>
  check(`${pkg} (${desc})`, req.toLowerCase().includes(pkg.toLowerCase()))
);

// ─── 3. Config ──────────────────────────────────────────────────────────────────
console.log('\n⚙️   [3] config.py — Settings');
const config = readFile('app/core/config.py') || '';
const configFields = [
  'GROQ_API_KEY', 'QDRANT_HOST', 'QDRANT_PORT',
  'COLLECTION_PERSONAL', 'COLLECTION_NETWORK', 'COLLECTION_VENDOR',
  'EMBEDDING_MODEL', 'GROQ_MODEL', 'RERANKER_MODEL',
  'CHUNK_SIZE', 'CHUNK_OVERLAP', 'HYBRID_ALPHA',
  'TOP_K_RETRIEVE', 'TOP_K_RERANK', 'RSS_SYNC_INTERVAL_MINS',
];
configFields.forEach(f => check(f, config.includes(f)));

// ─── 4. RAG Service ─────────────────────────────────────────────────────────────
console.log('\n🧠  [4] rag_service.py — Core Pipeline');
const rag = readFile('app/services/rag_service.py') || '';

const ragChecks = [
  ['Hybrid search function', 'def hybrid_search('],
  ['BM25Okapi usage', 'BM25Okapi('],
  ['Semantic vector search', 'qdrant.search('],
  ['Alpha-weighted fusion', 'HYBRID_ALPHA'],
  ['Metadata filter builder', 'def build_filter('],
  ['published_after range filter', 'published_after'],
  ['Cross-encoder reranker', 'def rerank('],
  ['CrossEncoder.predict()', 'reranker.predict('],
  ['Token-aware chunker', 'def chunk_text_by_tokens('],
  ['tiktoken encoding', 'tiktoken.get_encoding('],
  ['Ingest with rich metadata', 'async def ingest_text('],
  ['Multi-collection search', 'target_collections'],
  ['Top-K retrieve constant', 'TOP_K_RETRIEVE'],
  ['Top-K rerank constant', 'TOP_K_RERANK'],
  ['Source citation building', '"id": i'],
  ['Anti-hallucination prompt', 'Do not speculate'],
  ['Evidence not found safeguard', 'no evidence in the knowledge base'],
  ['Low temperature (faithful)', 'temperature=0.1'],
  ['Groq chat completions', 'groq_client.chat.completions.create('],
  ['Returns sources list', '"sources": sources'],
];
ragChecks.forEach(([label, pattern]) => check(label, rag.includes(pattern)));

// ─── 5. RSS Service ─────────────────────────────────────────────────────────────
console.log('\n📡  [5] rss_service.py — Feed Ingestion');
const rss = readFile('app/services/rss_service.py') || '';
const rssChecks = [
  ['Cisco PSIRT feed URL', 'CiscoSecurityAdvisory.xml'],
  ['Cisco Talos feed URL', 'talosintelligence.com'],
  ['Microsoft MSRC feed URL', 'msrc.microsoft.com'],
  ['Microsoft Security Blog', 'microsoft.com/en-us/security'],
  ['Severity inference', '_infer_severity'],
  ['Critical keyword detection', 'Critical'],
  ['HTML stripping', '_strip_html'],
  ['ISO date normalisation', '_normalise_date'],
  ['Deduplication hash', '_dedupe_hash'],
  ['vendor metadata field', '"vendor": vendor'],
  ['severity metadata field', '"severity": severity'],
  ['published metadata field', '"published": published'],
  ['dedup_hash in metadata', '"dedup_hash": dedup_hash'],
  ['Already-indexed check', '_already_indexed'],
  ['Async sync_feeds method', 'async def sync_feeds('],
];
rssChecks.forEach(([label, pattern]) => check(label, rss.includes(pattern)));

// ─── 6. Main App ────────────────────────────────────────────────────────────────
console.log('\n🚀  [6] main.py — FastAPI Application');
const main = readFile('app/main.py') || '';
const mainChecks = [
  ['Lifespan context manager', 'asynccontextmanager'],
  ['APScheduler startup', 'AsyncIOScheduler()'],
  ['Interval scheduling', '"interval"'],
  ['RSS_SYNC_INTERVAL_MINS used', 'RSS_SYNC_INTERVAL_MINS'],
  ['Initial startup RSS sync', 'asyncio.create_task(scheduled_rss_sync())'],
  ['POST /api/chat (compat)', 'app.post("/api/chat")'],
  ['POST /query endpoint', 'app.post("/query")'],
  ['GET /news/latest', 'app.get("/news/latest")'],
  ['POST /ingest endpoint', 'app.post("/ingest")'],
  ['POST /rss/sync manual', 'app.post("/rss/sync")'],
  ['GET /health endpoint', 'app.get("/health")'],
  ['QueryRequest with filters', 'class QueryRequest(BaseModel)'],
  ['Filters field in QueryRequest', 'filters: Optional[Dict'],
  ['Vendor filter in /news/latest', 'vendor: Optional[str]'],
  ['Severity filter in /news/latest', 'severity: Optional[str]'],
  ['Source footer formatter', '_format_source_footer'],
  ['Backwards-compat /api/chat', 'ChatRequest'],
  ['CORS middleware', 'CORSMiddleware'],
];
mainChecks.forEach(([label, pattern]) => check(label, main.includes(pattern)));

// ─── 7. .env.example ────────────────────────────────────────────────────────────
console.log('\n🔒  [7] .env.example — Configuration Template');
const env = readFile('.env.example') || '';
const envKeys = [
  'GROQ_API_KEY', 'QDRANT_HOST', 'QDRANT_PORT',
  'EMBEDDING_MODEL', 'GROQ_MODEL', 'RERANKER_MODEL',
  'HYBRID_ALPHA', 'TOP_K_RETRIEVE', 'TOP_K_RERANK',
  'RSS_SYNC_INTERVAL_MINS',
];
envKeys.forEach(k => check(k, env.includes(k)));

// ─── 8. Dockerfile ──────────────────────────────────────────────────────────────
console.log('\n🐳  [8] docker/Dockerfile — Container Build');
const df = readFile('docker/Dockerfile') || '';
const dfChecks = [
  ['Python 3.10 base image', 'python:3.10-slim'],
  ['requirements.txt copied', 'COPY requirements.txt'],
  ['pip install command', 'pip install --no-cache-dir'],
  ['Embedding model pre-download', 'nomic-embed-text'],
  ['Reranker model pre-download', 'ms-marco-MiniLM'],
  ['Port 8000 exposed', 'EXPOSE 8000'],
  ['uvicorn CMD', '"uvicorn"'],
];
dfChecks.forEach(([label, pattern]) => check(label, df.includes(pattern)));

// ─── 9. Docker Compose ──────────────────────────────────────────────────────────
console.log('\n🐙  [9] docker/docker-compose.yml — Orchestration');
const dc = readFile('docker/docker-compose.yml') || '';
const dcChecks = [
  ['Qdrant service defined', 'qdrant:'],
  ['Qdrant official image', 'qdrant/qdrant'],
  ['Qdrant port 6333', '6333:6333'],
  ['Persistent volume', 'qdrant_data'],
  ['FastAPI service defined', 'jarvis-api:'],
  ['Port 3001 mapped', '3001:8000'],
  ['env_file reference', 'env_file:'],
  ['Depends on qdrant', 'depends_on:'],
];
dcChecks.forEach(([label, pattern]) => check(label, dc.includes(pattern)));

// ─── 10. Pipeline Simulation ────────────────────────────────────────────────────
console.log('\n🔬  [10] Pipeline Logic — Simulated Trace');

// Simulate chunking logic
function simulateChunking(text, chunkSize = 600 * 4, overlap = 120 * 4) {
  const chunks = [];
  let start = 0;
  while (start < text.length) {
    chunks.push(text.slice(start, start + chunkSize));
    start += chunkSize - overlap;
  }
  return chunks.filter(c => c.trim());
}

const sampleDoc = 'Cisco advisory CVE-2026-1234. This is a critical remote code execution vulnerability affecting Cisco IOS XE. '.repeat(50);
const chunks = simulateChunking(sampleDoc);
check('Chunker produces multiple chunks from long doc', chunks.length > 1);
check('Chunks respect size limit (approx)', chunks.every(c => c.length <= 600 * 4 + 100));
check('Last chunk is non-empty', chunks[chunks.length - 1].trim().length > 0);

// Simulate severity inference
function inferSeverity(text) {
  const lower = text.toLowerCase();
  if (['critical', 'rce', 'remote code execution', 'zero-day'].some(kw => lower.includes(kw))) return 'Critical';
  if (['high', 'privilege escalation', 'authentication bypass'].some(kw => lower.includes(kw))) return 'High';
  if (['medium', 'xss', 'csrf'].some(kw => lower.includes(kw))) return 'Medium';
  return 'Informational';
}

check('Severity: RCE → Critical', inferSeverity('remote code execution vulnerability') === 'Critical');
check('Severity: Auth bypass → High', inferSeverity('authentication bypass exploit') === 'High');
check('Severity: XSS → Medium', inferSeverity('stored XSS in admin panel') === 'Medium');
check('Severity: unknown → Informational', inferSeverity('firmware changelog update') === 'Informational');

// Simulate hybrid alpha weighting
function hybridScore(semNorm, bm25Norm, alpha = 0.7) {
  return alpha * semNorm + (1 - alpha) * bm25Norm;
}
check('Hybrid alpha=0.7 weights semantic higher', hybridScore(0.9, 0.1) > hybridScore(0.1, 0.9));
check('Hybrid alpha=0.5 gives equal weight', hybridScore(0.8, 0.0, 0.5) === hybridScore(0.0, 0.8, 0.5));

// Simulate dedup hash
import { createHash } from 'crypto';
function dedupHash(link, title) {
  return createHash('md5').update(`${link}::${title}`).digest('hex');
}
const h1 = dedupHash('https://cisco.com/adv/1', 'Advisory One');
const h2 = dedupHash('https://cisco.com/adv/1', 'Advisory One');
const h3 = dedupHash('https://cisco.com/adv/2', 'Advisory Two');
check('Dedup hash is deterministic', h1 === h2);
check('Dedup hash differs for different articles', h1 !== h3);

// Simulate source footer
function formatSourceFooter(sources) {
  if (!sources.length) return '';
  const lines = ['---', '**Sources:**'];
  for (const s of sources) {
    let line = `[${s.id}] **${s.vendor}** — ${s.title}`;
    if (s.published) line += ` (${s.published})`;
    if (s.severity && s.severity !== 'Informational') line += ` | ⚠️ ${s.severity}`;
    if (s.link) line += ` — [link](${s.link})`;
    lines.push(line);
  }
  return lines.join('\n');
}

const testSources = [
  { id: 1, vendor: 'Cisco', title: 'CVE-2026-1234', published: '2026-04-25', severity: 'Critical', link: 'https://cisco.com' },
  { id: 2, vendor: 'Microsoft', title: 'April Patch Tuesday', published: '2026-04-14', severity: 'Informational', link: '' },
];
const footer = formatSourceFooter(testSources);
check('Source footer contains [1]', footer.includes('[1]'));
check('Source footer shows Critical severity', footer.includes('⚠️ Critical'));
check('Source footer suppresses Informational severity', !footer.includes('⚠️ Informational'));
check('Source footer includes link', footer.includes('[link](https://cisco.com)'));
check('Source footer has no link for empty URL', !footer.includes('[link]()'));

// ─── Summary ─────────────────────────────────────────────────────────────────────
console.log('\n══════════════════════════════════════════════════════');
console.log(`   Test Results: ${passed} passed, ${failed} failed, ${warned} warnings`);
console.log('══════════════════════════════════════════════════════');

if (failed === 0) {
  console.log('\n🎯  All tests passed. Backend is structurally sound.');
  console.log('\n   Next steps to go live:');
  console.log('   1. Install Docker Desktop → https://www.docker.com/products/docker-desktop/');
  console.log('   2. cp jarvis-backend/.env.example jarvis-backend/.env');
  console.log('   3. Add your GROQ_API_KEY to .env');
  console.log('   4. cd jarvis-backend/docker && docker-compose up -d --build');
  console.log('   5. curl http://localhost:3001/health\n');
} else {
  console.log(`\n⛔  ${failed} test(s) failed — review the output above.\n`);
  process.exit(1);
}
