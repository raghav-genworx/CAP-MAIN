const LANGUAGE_LABELS: Record<string, string> = {
  c: "C",
  "c++": "C++",
  cpp: "C++",
  java: "Java",
  python: "Python",
};

export function languageDisplayName(language: string) {
  const normalized = language.trim().toLowerCase();
  return LANGUAGE_LABELS[normalized] ?? language.trim().toUpperCase();
}
