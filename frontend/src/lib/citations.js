const citationPattern = /(?:evidence|finding)_[A-Za-z0-9]+/g;

function prose(markdown) {
  return String(markdown || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`\n]*`/g, "");
}

export function buildCitationContext(markdown) {
  const labels = {};
  const occurrences = {};
  let next = 1;
  for (const match of prose(markdown).matchAll(citationPattern)) {
    const referenceId = match[0];
    const label = labels[referenceId] || String(next++);
    labels[referenceId] = label;
    occurrences[referenceId] ||= [];
    occurrences[referenceId].push({
      index: occurrences[referenceId].length,
      label,
      offset: match.index,
    });
  }
  return { labels, occurrences };
}
