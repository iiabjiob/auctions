export function renderHelpMarkdown(markdown: string): string {
  const html: string[] = []
  let listOpen = false
  let blockquoteOpen = false

  const closeList = () => {
    if (!listOpen) return
    html.push('</ul>')
    listOpen = false
  }
  const closeBlockquote = () => {
    if (!blockquoteOpen) return
    html.push('</blockquote>')
    blockquoteOpen = false
  }
  const closeBlocks = () => {
    closeList()
    closeBlockquote()
  }

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) {
      closeBlocks()
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      closeBlocks()
      const marker = heading[1] ?? ''
      const title = heading[2] ?? ''
      const level = marker.length
      html.push(`<h${level}>${renderInlineMarkdown(title)}</h${level}>`)
      continue
    }

    const listItem = /^-\s+(.+)$/.exec(line)
    if (listItem) {
      closeBlockquote()
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${renderInlineMarkdown(listItem[1] ?? '')}</li>`)
      continue
    }

    const quote = /^>\s?(.+)$/.exec(line)
    if (quote) {
      closeList()
      if (!blockquoteOpen) {
        html.push('<blockquote>')
        blockquoteOpen = true
      }
      html.push(`<p>${renderInlineMarkdown(quote[1] ?? '')}</p>`)
      continue
    }

    closeBlocks()
    html.push(`<p>${renderInlineMarkdown(line)}</p>`)
  }

  closeBlocks()
  return html.join('')
}

export function renderInlineMarkdown(value: string): string {
  return escapeHtml(value).replace(/`([^`]+)`/g, '<code>$1</code>')
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
