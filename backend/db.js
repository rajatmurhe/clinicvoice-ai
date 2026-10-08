const Database = require('node:sqlite').DatabaseSync;
const fs = require('fs');
const path = require('path');

const db = new Database(path.join(__dirname, 'data', 'clinic.db'));

function ensureSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS faqs (
      id INTEGER PRIMARY KEY,
      question TEXT NOT NULL,
      answer TEXT NOT NULL,
      question_hi TEXT,
      question_mr TEXT
    )
  `);
  // Older databases lack the translated question columns; the table is fully
  // reseeded from faqs.json, so recreating it loses nothing.
  const cols = db.prepare('PRAGMA table_info(faqs)').all().map(function(c) { return c.name; });
  if (!cols.includes('question_hi') || !cols.includes('question_mr')) {
    db.exec('DROP TABLE faqs');
    db.exec(`
      CREATE TABLE faqs (
        id INTEGER PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        question_hi TEXT,
        question_mr TEXT
      )
    `);
  }
}

ensureSchema();

function seedFromJson() {
  const faqs = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'faqs.json'), 'utf8'));

  db.exec('DELETE FROM faqs');

  const insert = db.prepare('INSERT INTO faqs (id, question, answer, question_hi, question_mr) VALUES (?, ?, ?, ?, ?)');
  for (const faq of faqs) {
    insert.run(faq.id, faq.question, faq.answer, faq.question_hi || null, faq.question_mr || null);
  }

  console.log('Refreshed database with ' + faqs.length + ' FAQs from faqs.json.');
}

function getAllFaqs() {
  return db.prepare('SELECT id, question, answer, question_hi, question_mr FROM faqs').all();
}

module.exports = { db, seedFromJson, getAllFaqs };
