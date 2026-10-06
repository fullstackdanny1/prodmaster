package core

import "regexp"

// projectName matches the project naming convention from spec 4.1: lowercase
// letters, digits and hyphens, with dots separating subprojects ("y.import").
var projectName = regexp.MustCompile(`^[a-z0-9-]+(\.[a-z0-9-]+)*$`)

// IsProjectName reports whether s follows the project naming convention.
func IsProjectName(s string) bool { return projectName.MatchString(s) }

// EntryProject guesses which tag of a time entry is the project.
//
// When the timer is started from a Taskwarrior task, the Timewarrior hook tags
// the interval with the task description, the project and the task tags, in no
// guaranteed order. The description usually contains spaces or capitals, so
// the first tag that looks like a project name is taken. If none does, the
// first tag is returned; an entry without tags returns "".
func EntryProject(e TimeEntry) string {
	for _, t := range e.Tags {
		if IsProjectName(t) {
			return t
		}
	}
	if len(e.Tags) > 0 {
		return e.Tags[0]
	}
	return ""
}
