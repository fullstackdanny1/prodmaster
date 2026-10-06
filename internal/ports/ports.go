// Package ports defines the interfaces ("ports") between the application and
// the outside world (spec 9.3).
//
// The core and the UI depend only on these interfaces. Each external tool is
// plugged in through an adapter (package internal/adapters/...) that
// implements one of them. The interfaces describe the application's model, not
// the commands of a particular tool.
package ports

import (
	"os/exec"
	"time"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// Clock is defined in core (the rules need it); it is re-exported here so that
// all ports can be found in one place.
type Clock = core.Clock

// Calendar reads events and writes to the calendars that allow it.
type Calendar interface {
	// Events returns the events that overlap [from, to), sorted by start.
	Events(from, to time.Time) ([]core.Event, error)
	// AddEvent creates an event in the given calendar. It must fail for
	// calendars that are not writable (e.g. Google calendars).
	AddEvent(calendar string, e core.Event) error
}

// Tasks manages tasks, objectives and subtasks. Tasks are always addressed by
// UUID.
type Tasks interface {
	List(f core.TaskFilter) ([]core.Task, error)
	// Add creates a task from a line in Taskwarrior syntax
	// ("Tema 3 project:ia due:fri"), passed through as is.
	Add(raw string) (core.Task, error)
	// Modify applies a line in Taskwarrior syntax to an existing task.
	Modify(uuid string, raw string) error
	Complete(uuid string) error
	Delete(uuid string) error
	// AddSubtask creates a task and attaches it to parentUUID.
	AddSubtask(parentUUID string, raw string) (core.Task, error)
	Annotate(uuid string, text string) error
	// SetScheduled sets the scheduled time; nil clears it.
	SetScheduled(uuid string, t *time.Time) error
	Start(uuid string) error
	Stop(uuid string) error
}

// TimeTracker records worked time. Only one interval can be running.
type TimeTracker interface {
	// Start stops the running interval, if any, and starts a new one.
	Start(tags ...string) error
	// Stop ends the running interval. It is not an error if none is running.
	Stop() error
	// Active returns the running interval, or nil if none is running.
	Active() (*core.TimeEntry, error)
	// Entries returns the intervals that overlap [from, to), sorted by start.
	Entries(from, to time.Time) ([]core.TimeEntry, error)
	// Add records a finished interval retroactively.
	Add(e core.TimeEntry) error
}

// Habits reads habit status and logs results.
type Habits interface {
	Status(day time.Time) ([]core.Habit, error)
	Log(name string, day time.Time, result core.HabitResult) error
}

// Notes gives access to the Markdown notes. Paths are relative to the notes
// directory. Notes are never edited inside the application (spec 2.5).
type Notes interface {
	List() ([]core.NoteRef, error)
	Read(path string) (string, error)
	// CreateFromTemplate creates a note of the given kind from its template and
	// returns its path. The exact mapping kind -> location is defined in stage 5.
	CreateFromTemplate(kind, title string, vars map[string]string) (string, error)
	// AppendLine appends one line at the end of the file, creating it if needed.
	AppendLine(path, line string) error
	// UpdateAutoSection replaces only the generated section of the file
	// (see core.ReplaceAutoSection).
	UpdateAutoSection(path, content string) error
}

// Editor builds the command that opens a file in the external editor. The UI
// runs it with tea.ExecProcess, which suspends the TUI while the editor runs.
type Editor interface {
	Command(path string) *exec.Cmd
}

// Notifier sends desktop notifications.
type Notifier interface {
	Send(title, body string) error
}
