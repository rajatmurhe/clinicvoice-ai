const Database = require('node:sqlite').DatabaseSync;
const fs = require('fs');
const path = require('path');

const DB_PATH = process.env.FAQ_DB_PATH || path.join(__dirname, 'data', 'clinic.db');
const db = new Database(DB_PATH);
// Jest runs suites in parallel workers and they all open this file; WAL plus
// a busy timeout stops concurrent schema setup from tripping over locks.
db.exec('PRAGMA journal_mode = WAL');
db.exec('PRAGMA busy_timeout = 5000');

function ensureSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS faqs (
      id INTEGER NOT NULL,
      question TEXT NOT NULL,
      answer TEXT NOT NULL,
      question_hi TEXT,
      question_mr TEXT,
      clinic_id TEXT NOT NULL DEFAULT 'default',
      PRIMARY KEY (clinic_id, id)
    )
  `);
  // Older databases lack the translated question or clinic columns; the table
  // is fully reseeded from the JSON files, so recreating it loses nothing.
  const cols = db.prepare('PRAGMA table_info(faqs)').all().map(function(c) { return c.name; });
  const pk = db.prepare('PRAGMA table_info(faqs)').all().filter(function(c) { return c.pk > 0; }).map(function(c) { return c.name; }).sort();
  if (!cols.includes('question_hi') || !cols.includes('question_mr') || !cols.includes('clinic_id') || pk.join(',') !== 'clinic_id,id') {
    db.exec('DROP TABLE faqs');
    db.exec(`
      CREATE TABLE faqs (
        id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        question_hi TEXT,
        question_mr TEXT,
        clinic_id TEXT NOT NULL DEFAULT 'default',
        PRIMARY KEY (clinic_id, id)
      )
    `);
  }
}

ensureSchema();

function seedFromJson() {
  const faqs = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'faqs.json'), 'utf8'));

  db.exec('DELETE FROM faqs');

  const insert = db.prepare("INSERT INTO faqs (id, question, answer, question_hi, question_mr, clinic_id) VALUES (?, ?, ?, ?, ?, ?)");
  for (const faq of faqs) {
    insert.run(faq.id, faq.question, faq.answer, faq.question_hi || null, faq.question_mr || null, 'default');
  }

  // Per clinic FAQ overrides live next to the clinic configs so a second
  // clinic onboards without code changes.
  let clinicCount = 0;
  try {
    const clinicsDir = path.join(__dirname, '..', 'python-agents', 'clinics');
    for (const file of fs.readdirSync(clinicsDir)) {
      if (!file.endsWith('.json')) continue;
      const clinic = JSON.parse(fs.readFileSync(path.join(clinicsDir, file), 'utf8'));
      if (!clinic.faqs || !clinic.id) continue;
      for (const faq of clinic.faqs) {
        insert.run(faq.id, faq.question, faq.answer, null, null, clinic.id);
      }
      clinicCount++;
    }
  } catch (e) {
    // No clinics directory: single tenant deployments are fine without it.
  }

  console.log('Refreshed database with ' + faqs.length + ' FAQs and ' + clinicCount + ' clinic overrides.');
}

const FAQ_RETRIEVAL_SQL = 'SELECT id, question, answer, question_hi, question_mr FROM faqs WHERE clinic_id = ?';

function getAllFaqs(clinicId) {
  const cid = clinicId || 'default';
  return db.prepare(FAQ_RETRIEVAL_SQL).all(cid);
}

module.exports = { db, seedFromJson, getAllFaqs, FAQ_RETRIEVAL_SQL };
