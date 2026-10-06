package core

import "strings"

// Markers delimiting the generated part of the daily journal (spec 7.2).
const (
	AutoStart = "<!-- auto:start -->"
	AutoEnd   = "<!-- auto:end -->"
)

// ReplaceAutoSection returns doc with everything between AutoStart and AutoEnd
// replaced by content. Text outside the markers is never touched.
//
// If the markers are missing (or out of order), the section is appended at the
// end of the document so that nothing written by the user is lost.
func ReplaceAutoSection(doc, content string) string {
	content = strings.TrimRight(content, "\n")
	block := AutoStart + "\n" + content + "\n" + AutoEnd

	start := strings.Index(doc, AutoStart)
	end := strings.Index(doc, AutoEnd)
	if start < 0 || end < 0 || end < start {
		if doc != "" && !strings.HasSuffix(doc, "\n") {
			doc += "\n"
		}
		return doc + block + "\n"
	}
	return doc[:start] + block + doc[end+len(AutoEnd):]
}
