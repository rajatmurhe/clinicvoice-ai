const Database = require('node:sqlite').DatabaseSync;
const fs = require('fs');
const path = require('path');

const db = new Database(path.join(__dirname, 'data', 'clinic.db'));

db.exec(`
  CREATE TABLE IF NOT EXISTS faqs (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL
  )
`);

function seedFromJson() {
  const existing = db.prepare('SELECT COUNT(*) as count FROM faqs').get();
  if (existing.count > 0) {
    console.log('Database already seeded, skipping.');
    return;
  }

  const faqs = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'faqs.json'), 'utf8'));
  const insert = db.prepare('INSERT INTO faqs (id, question, answer) VALUES (?, ?, ?)');

  for (const faq of faqs) {
    insert.run(faq.id, faq.question, faq.answer);
  }

  console.log('Seeded ' + faqs.length + ' FAQs into SQLite.');
}

function getAllFaqs() {
  return db.prepare('SELECT id, question, answer FROM faqs').all();
}

module.exports = { db, seedFromJson, getAllFaqs };
