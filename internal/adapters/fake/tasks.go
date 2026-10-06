// Package fake contains in-memory implementations of every port. They are used
// by the tests (core rules, UI, contract tests) and can be selected in the
// configuration with the adapter name "fake" to try the UI without any tool
// installed. They hold no data on disk: everything is lost on exit.
package fake

import (
	"fmt"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// Tasks is an in-memory task list.
//
// It understands only a small subset of the Taskwarrior syntax, enough for
// tests: "project:x", "+tag", "-tag", "due:YYYY-MM-DD" (or RFC 3339) and
// "description:..."; every other word becomes part of the description.
type Tasks struct {
	mu    sync.Mutex
	clock core.Clock
	tasks []*core.Task
	next  int
}

func NewTasks(clock core.Clock) *Tasks { return &Tasks{clock: clock} }

func (s *Tasks) List(f core.TaskFilter) ([]core.Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []core.Task
	for _, t := range s.tasks {
		if t.Status != f.Status {
			continue
		}
		if f.Project != "" && t.Project != f.Project {
			continue
		}
		out = append(out, clone(*t))
	}
	return out, nil
}

func (s *Tasks) Add(raw string) (core.Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.add(raw)
}

func (s *Tasks) add(raw string) (core.Task, error) {
	s.next++
	t := &core.Task{UUID: fmt.Sprintf("00000000-0000-4000-8000-%012d", s.next)}
	if err := applyRaw(t, raw, true); err != nil {
		return core.Task{}, err
	}
	if t.Description == "" {
		return core.Task{}, fmt.Errorf("descriere lipsă")
	}
	s.tasks = append(s.tasks, t)
	return clone(*t), nil
}

func (s *Tasks) Modify(uuid, raw string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	return applyRaw(t, raw, false)
}

func (s *Tasks) Complete(uuid string) error { return s.setStatus(uuid, core.StatusCompleted) }
func (s *Tasks) Delete(uuid string) error   { return s.setStatus(uuid, core.StatusDeleted) }

func (s *Tasks) setStatus(uuid string, st core.TaskStatus) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	t.Status = st
	t.Active = false
	return nil
}

func (s *Tasks) AddSubtask(parentUUID, raw string) (core.Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	parent, err := s.find(parentUUID)
	if err != nil {
		return core.Task{}, err
	}
	child, err := s.add(raw)
	if err != nil {
		return core.Task{}, err
	}
	parent.Subtasks = append(parent.Subtasks, child.UUID)
	return child, nil
}

func (s *Tasks) Annotate(uuid, text string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	t.Annotations = append(t.Annotations, core.Annotation{Entry: s.clock.Now(), Text: text})
	return nil
}

func (s *Tasks) SetScheduled(uuid string, when *time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	if when == nil {
		t.Scheduled = nil
	} else {
		v := *when
		t.Scheduled = &v
	}
	return nil
}

// Start marks the task active and every other task inactive, like the single
// timer of Timewarrior. The fake does not record time; tests that need time
// combine it with fake.TimeTracker.
func (s *Tasks) Start(uuid string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	for _, o := range s.tasks {
		o.Active = false
	}
	t.Active = true
	return nil
}

func (s *Tasks) Stop(uuid string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, err := s.find(uuid)
	if err != nil {
		return err
	}
	t.Active = false
	return nil
}

func (s *Tasks) find(uuid string) (*core.Task, error) {
	for _, t := range s.tasks {
		if t.UUID == uuid {
			return t, nil
		}
	}
	return nil, fmt.Errorf("sarcină inexistentă: %s", uuid)
}

// applyRaw applies the supported subset of Taskwarrior syntax to t. When adding
// is false (modify), plain words replace the description only if there are
// any, like "task <uuid> modify project:x" keeps the description.
func applyRaw(t *core.Task, raw string, adding bool) error {
	var words []string
	for _, tok := range strings.Fields(raw) {
		switch {
		case strings.HasPrefix(tok, "project:"):
			t.Project = strings.TrimPrefix(tok, "project:")
		case strings.HasPrefix(tok, "description:"):
			words = append(words, strings.TrimPrefix(tok, "description:"))
		case strings.HasPrefix(tok, "due:"):
			v := strings.TrimPrefix(tok, "due:")
			if v == "" {
				t.Due = nil
				continue
			}
			d, err := parseDate(v)
			if err != nil {
				return err
			}
			t.Due = &d
		case len(tok) > 1 && tok[0] == '+':
			if !slices.Contains(t.Tags, tok[1:]) {
				t.Tags = append(t.Tags, tok[1:])
			}
		case len(tok) > 1 && tok[0] == '-':
			t.Tags = slices.DeleteFunc(t.Tags, func(s string) bool { return s == tok[1:] })
		default:
			words = append(words, tok)
		}
	}
	if len(words) > 0 || adding {
		t.Description = strings.Join(words, " ")
	}
	t.Kind = core.KindSimple
	if slices.Contains(t.Tags, "obiectiv") {
		t.Kind = core.KindObjective
	}
	return nil
}

func parseDate(v string) (time.Time, error) {
	if d, err := time.ParseInLocation("2006-01-02", v, time.Local); err == nil {
		return d, nil
	}
	if d, err := time.Parse(time.RFC3339, v); err == nil {
		return d, nil
	}
	return time.Time{}, fmt.Errorf("dată nerecunoscută de adaptorul fake: %q", v)
}

// clone copies a task so callers cannot modify the stored one through slices
// or pointers.
func clone(t core.Task) core.Task {
	t.Tags = slices.Clone(t.Tags)
	t.Subtasks = slices.Clone(t.Subtasks)
	t.Annotations = slices.Clone(t.Annotations)
	if t.Due != nil {
		d := *t.Due
		t.Due = &d
	}
	if t.Scheduled != nil {
		d := *t.Scheduled
		t.Scheduled = &d
	}
	return t
}
