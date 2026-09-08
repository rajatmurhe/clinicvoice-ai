interface Faq {
  id: number;
  question: string;
  answer: string;
}

async function getFaqs(): Promise<Faq[]> {
  const res = await fetch('http://localhost:3000/faqs', { cache: 'no-store' });
  if (!res.ok) {
    throw new Error('Failed to fetch FAQs');
  }
  return res.json();
}

export default async function Home() {
  const faqs = await getFaqs();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 px-6 py-16">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.8)]"></span>
          <h1 className="text-2xl font-bold tracking-tight">ClinicVoice AI</h1>
        </div>
        <p className="text-slate-500 text-sm mb-10">
          FAQ knowledge base, server-rendered via Next.js from a NestJS API
        </p>

        <div className="space-y-4">
          {faqs.map((faq) => (
            <div
              key={faq.id}
              className="bg-slate-900 border border-slate-800 rounded-2xl p-5"
            >
              <h2 className="font-semibold text-slate-100 mb-2">
                {faq.question}
              </h2>
              <p className="text-slate-400 text-sm leading-relaxed">
                {faq.answer}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
