#!/usr/bin/env node
/**
 * Checks Agentic Browsing readiness endpoints (/llms.txt and /.well-known/ard.json)
 * alongside the bundled Lighthouse agentic-browsing-config rule list.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log('Usage: node agentic-readiness-check.mjs [baseUrl=http://localhost:3000]');
  process.exit(0);
}
const baseUrl = (process.argv[2] || 'http://localhost:3000').replace(/\/$/, '');

async function checkEndpoint(url, label) {
  try {
    const res = await fetch(url);
    if (!res.ok) {
      console.log(`WARN [${label}] ${url} returned HTTP ${res.status}`);
      return false;
    }
    const text = await res.text();
    console.log(`PASS [${label}] ${url} (${text.length} bytes)`);
    return true;
  } catch (err) {
    console.error(`FAIL [${label}] ${url}: ${err.message}`);
    return false;
  }
}

const configPath = path.join(__dirname, '..', 'references', 'agentic-browsing-config.js');
const configExists = fs.existsSync(configPath);
console.log(`Agentic Lighthouse config present: ${configExists}`);

const llmsOk = await checkEndpoint(`${baseUrl}/llms.txt`, 'llms.txt');
const ardOk = await checkEndpoint(`${baseUrl}/.well-known/ard.json`, 'ard.json');

if (!llmsOk && !ardOk) {
  console.log('INFO: Neither /llms.txt nor /.well-known/ard.json exposed (optional for non-agentic sites, required for agentic readiness).');
}
