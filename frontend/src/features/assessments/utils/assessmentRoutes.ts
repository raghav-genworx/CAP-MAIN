export function slugify(text: string): string {
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^\w-]+/g, "")
    .replace(/--+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "");
}

export function assessmentPath(assessmentId: string, title?: string) {
  const slug = title ? slugify(title) : "assessment";
  return `/recruiter/assessments/${encodeURIComponent(slug)}/${encodeURIComponent(assessmentId)}`;
}

export function assessmentTestPath(assessmentId: string, testId: string, assessmentTitle?: string, testTitle?: string) {
  const aSlug = assessmentTitle ? slugify(assessmentTitle) : "assessment";
  const tSlug = testTitle ? slugify(testTitle) : "test";
  return `/recruiter/assessments/${encodeURIComponent(aSlug)}/${encodeURIComponent(assessmentId)}/tests/${encodeURIComponent(tSlug)}/${encodeURIComponent(testId)}`;
}
