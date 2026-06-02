import DOMPurify from "dompurify";
import { marked } from "marked";

const ALLOWED_TAGS = [
  "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
  "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "hr",
  "table", "thead", "tbody", "tr", "th", "td", "img", "video", "source",
];

const ALLOWED_ATTR = [
  "href", "target", "rel", "src", "alt", "controls", "playsinline",
  "muted", "loop", "preload", "type", "style",
];

/** Render trusted-but-sanitized markdown to an HTML string for v-html. */
export function renderMarkdown(content: string): string {
  if (!content) return "";
  const html = marked(content, { breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
}
