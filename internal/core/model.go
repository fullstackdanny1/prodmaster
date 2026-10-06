// Package core holds the application's data model and its rules
// (spec sections 4 and 5).
//
// The core knows nothing about khal, Taskwarrior, Timewarrior, harsh or any
// other tool. Adapters translate tool data into the types below; the UI and the
// rules only ever see these types. This is what makes a tool replaceable: a new
// adapter only has to produce the same types.
package core

import "time"

// Event is something that happens at a fixed time (spec 4.2). Both plain
// events (lectures, appointments) and work blocks are Events; a work block is
// simply an Event whose Calendar is the configured blocks calendar.
type Event struct {
	ID          string // stable identifier from the calendar tool (e.g. iCal UID)
	Calendar    string // calendar name, e.g. "cursuri", "personal", "plan"
	Title       string
	Description string
	Location    string
	Start       time.Time
	End         time.Time
	AllDay      bool
}

// TaskKind is the classification from spec 4.2. The adapter decides it using
// the rules there (duration > objective > simple).
type TaskKind int

const (
	KindSimple    TaskKind = iota // plain task, done when checked
	KindObjective                 // judged by outcome, not by subtasks
	KindDuration                  // has a time target inside a horizon window
)

// TaskStatus mirrors the life cycle of a task.
type TaskStatus int

const (
	StatusPending TaskStatus = iota
	StatusCompleted
	StatusDeleted
)

// Horizon is the measuring window of a duration task (spec 4.3).
type Horizon string

const (
	HorizonNone  Horizon = ""
	HorizonDay   Horizon = "zi"
	HorizonWeek  Horizon = "saptamana"
	HorizonMonth Horizon = "luna"
)

// Annotation is a timestamped free-text note attached to a task. Annotations
// are used to link notes (a path ending in .md) and to record what happened
// (e.g. "neatins", "lucrat în blocul din 2026-10-05").
type Annotation struct {
	Entry time.Time
	Text  string
}

// Task is a unit of work (spec 4.2). It is always identified by UUID, never by
// the numeric IDs a tool may show (spec 14).
type Task struct {
	UUID        string
	Description string
	Project     string // "" when the task has no project
	Kind        TaskKind
	Status      TaskStatus
	Tags        []string
	Due         *time.Time // nil = no deadline
	Scheduled   *time.Time // used to "lend" subtasks to a work block (spec 4.4)
	Target      time.Duration
	Horizon     Horizon
	Subtasks    []string // UUIDs of the subtasks owned by this task
	Annotations []Annotation
	Active      bool // the timer is running on this task
}

// TaskFilter narrows Tasks.List. Zero values mean "no restriction", except
// Status, whose zero value is StatusPending (the most common query).
type TaskFilter struct {
	Status  TaskStatus
	Project string
}

// TimeEntry is one tracked interval (spec 5.1). End == nil means the interval
// is still running.
type TimeEntry struct {
	Start time.Time
	End   *time.Time
	Tags  []string
}

// Running reports whether the entry has no end yet.
func (e TimeEntry) Running() bool { return e.End == nil }

// HabitResult is what was logged for a habit on a given day.
type HabitResult int

const (
	HabitNone    HabitResult = iota // nothing logged yet
	HabitDone                       // "y"
	HabitSkipped                    // "s": does not break the streak
	HabitFailed                     // "n"
)

// Frequency says how often a habit should be done: Times every PeriodDays.
// "1" daily = {1, 1}; "3/7" = {3, 7}; "1w" = {1, 7}; "2/30" = {2, 30}.
type Frequency struct {
	Times      int
	PeriodDays int
}

// Habit is a repeated activity measured by consistency (spec 4.6).
type Habit struct {
	Name         string
	Group        string // heading in the habits file, e.g. "Igienă"
	Frequency    Frequency
	Today        HabitResult
	DoneInPeriod int // how many times it was done in the current period
	Streak       int // consecutive days the habit has been kept
}

// NoteRef identifies a Markdown note on disk.
type NoteRef struct {
	Path    string // relative to the notes directory, e.g. "proiecte/ia.md"
	ModTime time.Time
}
