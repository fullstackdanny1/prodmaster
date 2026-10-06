package fake

import (
	"fmt"
	"os/exec"
	"slices"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// ---------------------------------------------------------------- Calendar

// Calendar is an in-memory set of calendars. Only calendars listed as writable
// accept new events, like the real configuration (spec 3).
type Calendar struct {
	mu       sync.Mutex
	writable []string
	events   []core.Event
	next     int
}

func NewCalendar(writable ...string) *Calendar { return &Calendar{writable: writable} }

// Seed inserts events directly, bypassing the writable check (used to simulate
// read-only calendars such as Google in tests).
func (c *Calendar) Seed(events ...core.Event) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.events = append(c.events, events...)
}

func (c *Calendar) Events(from, to time.Time) ([]core.Event, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	var out []core.Event
	for _, e := range c.events {
		if e.Start.Before(to) && e.End.After(from) {
			out = append(out, e)
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Start.Before(out[j].Start) })
	return out, nil
}

func (c *Calendar) AddEvent(calendar string, e core.Event) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !slices.Contains(c.writable, calendar) {
		return fmt.Errorf("calendarul %q nu permite scriere", calendar)
	}
	if !e.End.After(e.Start) {
		return fmt.Errorf("eveniment invalid: sfârșitul trebuie să fie după început")
	}
	c.next++
	e.ID = fmt.Sprintf("fake-%d", c.next)
	e.Calendar = calendar
	c.events = append(c.events, e)
	return nil
}

// ---------------------------------------------------------------- Habits

// Habits is an in-memory habit list with a log of results per day. It does not
// compute streaks or periods (that is real tool / core behaviour); tests set
// those fields directly through the Habits slice when they need them.
type Habits struct {
	mu     sync.Mutex
	Habits []core.Habit
	log    map[string]core.HabitResult // key: day + "\x00" + name
}

func NewHabits(habits ...core.Habit) *Habits {
	return &Habits{Habits: habits, log: map[string]core.HabitResult{}}
}

func dayKey(name string, day time.Time) string { return day.Format("2006-01-02") + "\x00" + name }

func (h *Habits) Status(day time.Time) ([]core.Habit, error) {
	h.mu.Lock()
	defer h.mu.Unlock()
	out := slices.Clone(h.Habits)
	for i := range out {
		out[i].Today = h.log[dayKey(out[i].Name, day)]
	}
	return out, nil
}

func (h *Habits) Log(name string, day time.Time, result core.HabitResult) error {
	h.mu.Lock()
	defer h.mu.Unlock()
	if !slices.ContainsFunc(h.Habits, func(x core.Habit) bool { return x.Name == name }) {
		return fmt.Errorf("obicei inexistent: %q", name)
	}
	h.log[dayKey(name, day)] = result
	return nil
}

// ---------------------------------------------------------------- Notes

// Notes is an in-memory notes directory. Templates map a kind to its text;
// {{titlu}}, {{data}}, {{proiect}} and any other key in vars are replaced.
type Notes struct {
	mu        sync.Mutex
	clock     core.Clock
	files     map[string]string
	mtimes    map[string]time.Time
	Templates map[string]string
}

func NewNotes(clock core.Clock) *Notes {
	return &Notes{clock: clock, files: map[string]string{}, mtimes: map[string]time.Time{}, Templates: map[string]string{}}
}

func (n *Notes) write(path, content string) {
	n.files[path] = content
	n.mtimes[path] = n.clock.Now()
}

func (n *Notes) List() ([]core.NoteRef, error) {
	n.mu.Lock()
	defer n.mu.Unlock()
	var out []core.NoteRef
	for p := range n.files {
		out = append(out, core.NoteRef{Path: p, ModTime: n.mtimes[p]})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Path < out[j].Path })
	return out, nil
}

func (n *Notes) Read(path string) (string, error) {
	n.mu.Lock()
	defer n.mu.Unlock()
	c, ok := n.files[path]
	if !ok {
		return "", fmt.Errorf("notiță inexistentă: %s", path)
	}
	return c, nil
}

// CreateFromTemplate stores the note at "<kind>/<title>.md". The real location
// rules are defined in stage 5; the fake only needs to be deterministic.
func (n *Notes) CreateFromTemplate(kind, title string, vars map[string]string) (string, error) {
	n.mu.Lock()
	defer n.mu.Unlock()
	tpl, ok := n.Templates[kind]
	if !ok {
		return "", fmt.Errorf("șablon inexistent: %q", kind)
	}
	path := kind + "/" + title + ".md"
	if _, exists := n.files[path]; exists {
		return "", fmt.Errorf("notița există deja: %s", path)
	}
	all := map[string]string{"titlu": title, "data": n.clock.Now().Format("2006-01-02")}
	for k, v := range vars {
		all[k] = v
	}
	for k, v := range all {
		tpl = strings.ReplaceAll(tpl, "{{"+k+"}}", v)
	}
	n.write(path, tpl)
	return path, nil
}

func (n *Notes) AppendLine(path, line string) error {
	n.mu.Lock()
	defer n.mu.Unlock()
	c := n.files[path]
	if c != "" && !strings.HasSuffix(c, "\n") {
		c += "\n"
	}
	n.write(path, c+line+"\n")
	return nil
}

func (n *Notes) UpdateAutoSection(path, content string) error {
	n.mu.Lock()
	defer n.mu.Unlock()
	c, ok := n.files[path]
	if !ok {
		return fmt.Errorf("notiță inexistentă: %s", path)
	}
	n.write(path, core.ReplaceAutoSection(c, content))
	return nil
}

// ---------------------------------------------------------------- Editor, Notifier

// Editor returns a command that does nothing ("true"), so the UI flow of
// suspending and resuming can be exercised without a real editor.
type Editor struct{ Opened []string }

func (e *Editor) Command(path string) *exec.Cmd {
	e.Opened = append(e.Opened, path)
	return exec.Command("true", path)
}

// Notification is one message recorded by the fake Notifier.
type Notification struct{ Title, Body string }

// Notifier records notifications instead of showing them.
type Notifier struct {
	mu   sync.Mutex
	Sent []Notification
}

func (n *Notifier) Send(title, body string) error {
	n.mu.Lock()
	defer n.mu.Unlock()
	n.Sent = append(n.Sent, Notification{title, body})
	return nil
}
