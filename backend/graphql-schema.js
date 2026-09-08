const { buildSchema } = require('graphql');
const { getAllFaqs } = require('./db');

const schema = buildSchema(`
  type Faq {
    id: Int
    question: String
    answer: String
  }

  type Query {
    faqs: [Faq]
    faq(id: Int!): Faq
  }
`);

const root = {
  faqs: () => {
    return getAllFaqs();
  },
  faq: ({ id }) => {
    const all = getAllFaqs();
    return all.find(function(f) { return f.id === id; });
  }
};

module.exports = { schema, root };
