package core

import (
	"testing"
	"time"
)

func TestNormalizeColor(t *testing.T) {
	cases := []struct {
		in, want string
		ok       bool
	}{
		{"green", "2", true},
		{"Blue", "4", true},
		{"bright-red", "9", true},
		{"brightred", "9", true},
		{"grey", "8", true},
		{"208", "208", true},
		{"0", "0", true},
		{"255", "255", true},
		{"256", "", false},
		{"-1", "", false},
		{"#E5A50A", "#e5a50a", true},
		{"#abc", "#abc", true},
		{"#abcd", "", false},
		{"verde", "", false},
		{"", "", false},
	}
	for _, c := range cases {
		got, err := NormalizeColor(c.in)
		if (err == nil) != c.ok {
			t.Errorf("NormalizeColor(%q) err = %v, want ok=%v", c.in, err, c.ok)
			continue
		}
		if got != c.want {
			t.Errorf("NormalizeColor(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestPaletteFallsBackToDefault(t *testing.T) {
	p := Palette{Default: "4", Projects: map[string]string{"ia": "2", "inexistent": "208"}}
	if got := p.Color("ia"); got != "2" {
		t.Errorf("ia: got %q", got)
	}
	if got := p.Color("rust"); got != "4" {
		t.Errorf("rust (no own colour): got %q, want default", got)
	}
	// A colour for a project that does not exist yet applies once it appears.
	if got := p.Color("inexistent"); got != "208" {
		t.Errorf("future project: got %q", got)
	}
}

func TestIsProjectName(t *testing.T) {
	good := []string{"ia", "proiect-y", "y.import", "rust2", "a.b.c"}
	bad := []string{"", "IA", "proiect y", "inteligență", "y.", ".y", "y..z"}
	for _, s := range good {
		if !IsProjectName(s) {
			t.Errorf("%q should be a project name", s)
		}
	}
	for _, s := range bad {
		if IsProjectName(s) {
			t.Errorf("%q should not be a project name", s)
		}
	}
}

func TestEntryProject(t *testing.T) {
	cases := []struct {
		tags []string
		want string
	}{
		{[]string{"Lucrez la proiectul y", "proiect-y"}, "proiect-y"},
		{[]string{"ia"}, "ia"},
		{[]string{"Doar Descriere"}, "Doar Descriere"},
		{nil, ""},
	}
	for _, c := range cases {
		if got := EntryProject(TimeEntry{Tags: c.tags}); got != c.want {
			t.Errorf("EntryProject(%v) = %q, want %q", c.tags, got, c.want)
		}
	}
}

func TestReplaceAutoSection(t *testing.T) {
	doc := "# 2026-10-06\n\n" + AutoStart + "\nvechi\n" + AutoEnd + "\n\n## Reflecții\nscris de mine\n"
	got := ReplaceAutoSection(doc, "nou\n")
	want := "# 2026-10-06\n\n" + AutoStart + "\nnou\n" + AutoEnd + "\n\n## Reflecții\nscris de mine\n"
	if got != want {
		t.Errorf("got:\n%s\nwant:\n%s", got, want)
	}
}

func TestReplaceAutoSectionWithoutMarkersAppends(t *testing.T) {
	got := ReplaceAutoSection("text", "nou")
	want := "text\n" + AutoStart + "\nnou\n" + AutoEnd + "\n"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestFixedClock(t *testing.T) {
	t0 := time.Date(2026, 10, 6, 9, 0, 0, 0, time.Local)
	c := &FixedClock{T: t0}
	c.Advance(90 * time.Minute)
	if want := t0.Add(90 * time.Minute); !c.Now().Equal(want) {
		t.Errorf("got %v, want %v", c.Now(), want)
	}
}
