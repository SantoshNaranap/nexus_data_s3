import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import { cleanContent } from '../utils/contentCleaner'

interface MarkdownMessageProps {
  content: string
}

export default function MarkdownMessage({ content }: MarkdownMessageProps) {
  // Clean the content to remove emojis and AI-ish patterns
  const cleanedContent = cleanContent(content)

  const components: Components = {
    // Paragraphs - cleaner spacing
    p: ({ children }) => (
      <p className="mb-4 last:mb-0 leading-relaxed text-gray-800 dark:text-gray-200">{children}</p>
    ),

    // Headings - more subtle, professional look
    h1: ({ children }) => (
      <h1 className="text-xl font-semibold mb-3 mt-5 first:mt-0 text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-lg font-semibold mb-3 mt-5 first:mt-0 text-gray-900 dark:text-white">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-base font-semibold mb-2 mt-4 first:mt-0 text-gray-900 dark:text-white">{children}</h3>
    ),

    // Lists - cleaner bullets
    ul: ({ children }) => (
      <ul className="list-disc list-outside ml-5 mb-4 space-y-1.5 text-gray-800 dark:text-gray-200">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal list-outside ml-5 mb-4 space-y-1.5 text-gray-800 dark:text-gray-200">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed pl-1">{children}</li>
    ),

    // Code blocks - cleaner look
    code: ({ className, children, ...props }) => {
      const isInline = !className

      if (isInline) {
        return (
          <code
            className="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono"
            {...props}
          >
            {children}
          </code>
        )
      }

      return (
        <code
          className={`${className} block bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-gray-200 p-4 rounded-lg my-4 overflow-x-auto font-mono text-sm leading-relaxed border border-gray-200 dark:border-gray-700`}
          {...props}
        >
          {children}
        </code>
      )
    },

    pre: ({ children }) => (
      <pre className="bg-gray-50 dark:bg-gray-800 rounded-lg my-4 overflow-hidden border border-gray-200 dark:border-gray-700">
        {children}
      </pre>
    ),

    // Blockquotes - subtle styling
    blockquote: ({ children }) => (
      <blockquote className="border-l-3 border-gray-300 dark:border-gray-600 pl-4 my-4 text-gray-600 dark:text-gray-400">
        {children}
      </blockquote>
    ),

    // Tables - clean, minimal design
    table: ({ children }) => (
      <div className="overflow-x-auto my-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">{children}</thead>
    ),
    tbody: ({ children }) => (
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {children}
      </tbody>
    ),
    tr: ({ children }) => <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">{children}</tr>,
    th: ({ children }) => (
      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
        {children}
      </td>
    ),

    // Links - subtle
    a: ({ children, href }) => (
      <a
        href={href}
        className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 underline decoration-blue-300 dark:decoration-blue-600 underline-offset-2"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    ),

    // Horizontal rule - subtle
    hr: () => (
      <hr className="my-6 border-gray-200 dark:border-gray-700" />
    ),

    // Strong/Bold
    strong: ({ children }) => (
      <strong className="font-semibold text-gray-900 dark:text-white">{children}</strong>
    ),

    // Emphasis/Italic
    em: ({ children }) => (
      <em className="italic text-gray-700 dark:text-gray-300">{children}</em>
    ),
  }

  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  )
}
