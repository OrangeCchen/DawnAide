/**
 * highlightMissing — 将 LLM 输出中的占位符标红
 *
 * 匹配格式：【需补充：任意说明】 或 【需补充】
 * 替换为：<mark class="info-missing">【需补充：...】</mark>
 *
 * 在 markdown-it 渲染完成后，对输出 HTML 调用此函数做后处理。
 */

const MISSING_PATTERN = /【需补充[：:]?[^】]*】/g

export function highlightMissing(html: string): string {
  if (!html.includes('【需补充')) return html
  return html.replace(
    MISSING_PATTERN,
    (match) => `<mark class="info-missing">${match}</mark>`,
  )
}
