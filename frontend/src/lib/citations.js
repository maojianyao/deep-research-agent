const citationPattern = /(?:evidence|finding)_[A-Za-z0-9_]+/g;

function prose(markdown) {
  return String(markdown || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]*`/g, "");
}

export function buildCitationContext(markdown, fallbackIds = [], sections = []) {
  const labels = {};
  const occurrences = {};
  let next = 1;

  function addOccurrence(referenceId, {
    source = "report",
    itemId = "",
    offset = -1,
    itemIndex = 0,
  } = {}) {
    const label = labels[referenceId] || String(next++);
    labels[referenceId] = label;
    occurrences[referenceId] ||= [];
    occurrences[referenceId].push({
      index: occurrences[referenceId].length,
      label,
      offset,
      source,
      itemId,
      itemIndex,
    });
  }

  function addText(text, source, itemId) {
    let itemIndex = 0;
    for (const match of prose(text).matchAll(citationPattern)) {
      addOccurrence(match[0], {
        source,
        itemId,
        offset: match.index,
        itemIndex: itemIndex++,
      });
    }
  }

  addText(markdown, "report", "");
  for (const section of sections) {
    addText(section.markdown, section.source, section.itemId);
    if (section.referenceId) {
      addOccurrence(section.referenceId, {
        source: section.source,
        itemId: section.itemId,
      });
    }
  }
  for (const referenceId of fallbackIds) {
    if (!labels[referenceId]) addOccurrence(referenceId);
  }
  return { labels, occurrences };
}
