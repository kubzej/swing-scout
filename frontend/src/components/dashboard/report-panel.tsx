import ReactMarkdown, { type Components } from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';

interface ReportPanelProps {
  reportContent: string | null;
}

const mdComponents: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold text-foreground mt-0 mb-1 tracking-tight">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground mt-7 mb-3 pb-1.5 border-b border-border">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-foreground mt-4 mb-1.5">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-sm text-foreground/80 leading-relaxed mb-2">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-foreground">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="text-xs text-muted-foreground/60 not-italic">{children}</em>
  ),
  ul: ({ children }) => (
    <ul className="my-1.5 space-y-1 pl-0 list-none">{children}</ul>
  ),
  li: ({ children }) => (
    <li className="text-sm text-foreground/80 flex gap-1.5 items-baseline">{children}</li>
  ),
  table: ({ children }) => (
    <div className="report-table overflow-x-auto my-3">
      <table className="w-full text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead>{children}</thead>
  ),
  th: ({ children }) => (
    <th className="text-[11px] font-medium text-muted-foreground text-left pb-2 pr-6 border-b border-border">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="py-2 pr-6 text-sm text-foreground/90 border-b border-border/20">{children}</td>
  ),
  tr: ({ children }) => (
    <tr className="hover:bg-white/[0.02] transition-colors">{children}</tr>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-muted-foreground underline underline-offset-2 decoration-border hover:text-foreground hover:decoration-foreground/40 transition-colors"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="border-border/40 my-4" />,
};

export function ReportPanel({ reportContent }: ReportPanelProps) {
  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 p-6 shadow-lg shadow-black/10 ring-soft">
      <div className="mb-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">
        Report
      </div>

      {reportContent ? (
        <div className="report-content max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={mdComponents}>
            {reportContent}
          </ReactMarkdown>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Report zatím není dostupný. Pokud run běží, objeví se po dokončení.
        </p>
      )}
    </section>
  );
}
