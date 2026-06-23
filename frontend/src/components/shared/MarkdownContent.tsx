import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownContentProps {
  content?: string | null;
  className?: string;
  placeholder?: string;
}

const isExternalHref = (href: string): boolean => /^https?:\/\//i.test(href);

const joinClasses = (...classNames: Array<string | undefined | null | false>): string =>
  classNames.filter(Boolean).join(' ');

const markdownComponents: Components = {
  h1: ({ className, ...props }) => (
    <h1
      className={joinClasses('mt-1 text-xl font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={joinClasses('mt-1 text-lg font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={joinClasses('mt-1 text-base font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={joinClasses('mt-1 text-sm font-semibold tracking-tight', className)}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p className={joinClasses('leading-6 [&:not(:first-child)]:mt-3', className)} {...props} />
  ),
  a: ({ className, href, ...props }) => {
    const isExternal = href ? isExternalHref(href) : false;
    return (
      <a
        className={joinClasses('font-medium text-blue-600 underline underline-offset-4', className)}
        href={href}
        rel={isExternal ? 'noreferrer noopener' : undefined}
        target={isExternal ? '_blank' : undefined}
        {...props}
      />
    );
  },
  ul: ({ className, ...props }) => (
    <ul
      className={joinClasses('ml-5 list-disc space-y-1 [&:not(:first-child)]:mt-3', className)}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={joinClasses('ml-5 list-decimal space-y-1 [&:not(:first-child)]:mt-3', className)}
      {...props}
    />
  ),
  li: ({ className, ...props }) => <li className={joinClasses('pl-1', className)} {...props} />,
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={joinClasses(
        'mt-3 border-l-2 border-border/80 pl-4 italic text-muted-foreground',
        className,
      )}
      {...props}
    />
  ),
  code: ({ className, ...props }) => (
    <code
      className={joinClasses('rounded bg-muted px-1.5 py-0.5 font-mono text-[0.875em]', className)}
      {...props}
    />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={joinClasses(
        'mt-3 overflow-x-auto rounded-md bg-slate-950 px-3 py-2 font-mono text-sm text-slate-50',
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr className={joinClasses('my-4 border-border', className)} {...props} />
  ),
  table: ({ className, ...props }) => (
    <div className="my-4 overflow-x-auto">
      <table
        className={joinClasses('w-full border-collapse text-left text-sm', className)}
        {...props}
      />
    </div>
  ),
  thead: ({ className, ...props }) => (
    <thead className={joinClasses('border-b border-border', className)} {...props} />
  ),
  tbody: ({ className, ...props }) => (
    <tbody className={joinClasses('[&_tr:last-child]:border-0', className)} {...props} />
  ),
  tr: ({ className, ...props }) => (
    <tr className={joinClasses('border-b border-border/70', className)} {...props} />
  ),
  th: ({ className, ...props }) => (
    <th className={joinClasses('px-3 py-2 font-semibold', className)} {...props} />
  ),
  td: ({ className, ...props }) => (
    <td className={joinClasses('px-3 py-2 align-top', className)} {...props} />
  ),
};

export const MarkdownContent = ({
  content,
  className,
  placeholder = '—',
}: MarkdownContentProps) => {
  if (!content?.trim()) {
    return (
      <div
        className={joinClasses(
          'rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground',
          className,
        )}
      >
        {placeholder}
      </div>
    );
  }

  return (
    <div
      className={joinClasses(
        'rounded-md border bg-muted/30 px-3 py-2 text-sm text-foreground',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
};
