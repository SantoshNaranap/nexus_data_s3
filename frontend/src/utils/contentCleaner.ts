/**
 * Content Cleaner - Removes AI-ish patterns and emojis from responses
 * for a cleaner, more professional look.
 */

// Common emoji ranges and patterns to remove
const EMOJI_REGEX = /[\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|[\u{1F1E0}-\u{1F1FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{FE00}-\u{FE0F}]|[\u{1F900}-\u{1F9FF}]|[\u{1FA00}-\u{1FA6F}]|[\u{1FA70}-\u{1FAFF}]|[\u{231A}-\u{231B}]|[\u{23E9}-\u{23F3}]|[\u{23F8}-\u{23FA}]|[\u{25AA}-\u{25AB}]|[\u{25B6}]|[\u{25C0}]|[\u{25FB}-\u{25FE}]|[\u{2614}-\u{2615}]|[\u{2648}-\u{2653}]|[\u{267F}]|[\u{2693}]|[\u{26A1}]|[\u{26AA}-\u{26AB}]|[\u{26BD}-\u{26BE}]|[\u{26C4}-\u{26C5}]|[\u{26CE}]|[\u{26D4}]|[\u{26EA}]|[\u{26F2}-\u{26F3}]|[\u{26F5}]|[\u{26FA}]|[\u{26FD}]|[\u{2702}]|[\u{2705}]|[\u{2708}-\u{270D}]|[\u{270F}]|[\u{2712}]|[\u{2714}]|[\u{2716}]|[\u{271D}]|[\u{2721}]|[\u{2728}]|[\u{2733}-\u{2734}]|[\u{2744}]|[\u{2747}]|[\u{274C}]|[\u{274E}]|[\u{2753}-\u{2755}]|[\u{2757}]|[\u{2763}-\u{2764}]|[\u{2795}-\u{2797}]|[\u{27A1}]|[\u{27B0}]|[\u{27BF}]|[\u{2934}-\u{2935}]|[\u{2B05}-\u{2B07}]|[\u{2B1B}-\u{2B1C}]|[\u{2B50}]|[\u{2B55}]|[\u{3030}]|[\u{303D}]|[\u{3297}]|[\u{3299}]/gu;

// Unicode symbols often used as decorative elements
const SYMBOL_REGEX = /[✓✔✗✘★☆●○◆◇▶►▼▾▲△→←↑↓⬆⬇⬅➡➤➔⚡⚠️❗❓❌✅☑️🔍📊📈📉💡🎯🔧⚙️🛠️💬🗨️📝📋🔗🌐💻🖥️📱⌨️🔒🔓📁📂📄📃✨🚀🎉🎊👋👍👎💪🤔🙏❤️💯🔥⭐]/g;

// Status message patterns (italicized or with asterisks)
const STATUS_PATTERNS = [
  /^\*[^*]+\.\.\.\*\s*$/gm,  // *Connecting...* at start of line
  /^\*[^*]+\*\s*$/gm,        // *Any italicized text* at start of line
  /^_[^_]+\.\.\._\s*$/gm,    // _Connecting..._ (underscore italics)
  /^Connecting to \w+\.\.\.\s*$/gim,
  /^Found relevant data\.\.\.\s*$/gim,
  /^Querying [^.]+\.\.\.\s*$/gim,
  /^Searching [^.]+\.\.\.\s*$/gim,
  /^Loading [^.]+\.\.\.\s*$/gim,
  /^Processing [^.]+\.\.\.\s*$/gim,
  /^Analyzing [^.]+\.\.\.\s*$/gim,
];

// Clean up excessive blank lines
const EXCESSIVE_NEWLINES = /\n{3,}/g;

// Clean up lines that are just dashes or equals (decorative separators)
const DECORATIVE_SEPARATORS = /^[-=]{5,}$/gm;

/**
 * Cleans content by removing emojis, symbols, and AI-ish patterns
 */
export function cleanContent(content: string): string {
  if (!content) return content;

  let cleaned = content;

  // Remove emojis
  cleaned = cleaned.replace(EMOJI_REGEX, '');

  // Remove common symbols used decoratively
  cleaned = cleaned.replace(SYMBOL_REGEX, '');

  // Remove status message patterns
  for (const pattern of STATUS_PATTERNS) {
    cleaned = cleaned.replace(pattern, '');
  }

  // Remove decorative separators
  cleaned = cleaned.replace(DECORATIVE_SEPARATORS, '');

  // Clean up excessive newlines
  cleaned = cleaned.replace(EXCESSIVE_NEWLINES, '\n\n');

  // Trim leading/trailing whitespace
  cleaned = cleaned.trim();

  return cleaned;
}

/**
 * Light cleaning - only removes emojis, keeps structure
 */
export function removeEmojis(content: string): string {
  if (!content) return content;

  return content
    .replace(EMOJI_REGEX, '')
    .replace(SYMBOL_REGEX, '')
    .trim();
}

/**
 * Check if content appears to be a status/loading message
 */
export function isStatusMessage(content: string): boolean {
  const trimmed = content.trim();

  // Check for common status patterns
  if (/^\*[^*]+\.\.\.\*$/.test(trimmed)) return true;
  if (/^Connecting to/i.test(trimmed)) return true;
  if (/^Found relevant data/i.test(trimmed)) return true;
  if (/^Querying/i.test(trimmed)) return true;
  if (/^Searching/i.test(trimmed)) return true;
  if (/^Loading/i.test(trimmed)) return true;

  return false;
}
