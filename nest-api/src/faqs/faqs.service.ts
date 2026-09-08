import { Injectable } from '@nestjs/common';
import { DatabaseSync } from 'node:sqlite';
import * as path from 'path';

@Injectable()
export class FaqsService {
  private db: any;

  constructor() {
    const dbPath = path.join(__dirname, '..', '..', '..', 'backend', 'data', 'clinic.db');
    this.db = new DatabaseSync(dbPath);
  }

  findAll() {
    return this.db.prepare('SELECT id, question, answer FROM faqs').all();
  }

  findOne(id: number) {
    return this.db.prepare('SELECT id, question, answer FROM faqs WHERE id = ?').get(id);
  }
}
