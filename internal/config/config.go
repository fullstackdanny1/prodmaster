// Package config loads ~/.config/dashboard/config.toml (spec section 10).
//
// The configuration is the only file the application owns. Loading never
// fails because of a bad value that has a sensible fallback (e.g. an invalid
// colour): such problems are collected in Config.Warnings and shown in the
// status bar at start-up. Only a syntactically broken file is a hard error.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"github.com/BurntSushi/toml"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// Page names accepted by start_page and by the --page flag.
var Pages = []string{"agenda", "sarcini", "timp", "notite"}

// Config mirrors the TOML file. Field tags give the TOML key names.
type Config struct {
	General  General  `toml:"general"`
	Adapters Adapters `toml:"adapters"`
	Calendar Calendar `toml:"calendar"`
	Time     Time     `toml:"time"`
	Notes    Notes    `toml:"notes"`
	Notify   Notify   `toml:"notify"`
	Colors   Colors   `toml:"colors"`
	Habits   Habits   `toml:"habits"`

	// Palette is computed from Colors after validation; it is what the rest of
	// the application uses.
	Palette core.Palette `toml:"-"`
	// Warnings lists non-fatal problems found while loading.
	Warnings []string `toml:"-"`
	// Path is the file that was loaded ("" if defaults were used).
	Path string `toml:"-"`
}

type General struct {
	StartPage      string `toml:"start_page"`
	RefreshSeconds int    `toml:"refresh_seconds"`
	AgendaDays     int    `toml:"agenda_days"`
}

// Adapters selects the implementation of each port by name.
type Adapters struct {
	Calendar string `toml:"calendar"`
	Tasks    string `toml:"tasks"`
	Time     string `toml:"time"`
	Habits   string `toml:"habits"`
}

type Calendar struct {
	Tracked  []string          `toml:"tracked"`  // calendars with time tracking
	Blocks   string            `toml:"blocks"`   // calendar holding work blocks
	Writable []string          `toml:"writable"` // calendars the app may write to
	Projects map[string]string `toml:"projects"` // event title -> project
}

type Time struct {
	IncludeSubprojects bool   `toml:"include_subprojects"`
	MobileFile         string `toml:"mobile_file"`
}

type Notes struct {
	Dir       string `toml:"dir"`
	Templates string `toml:"templates"`
	Editor    string `toml:"editor"`
}

type Notify struct {
	MinutesBefore int `toml:"minutes_before"`
}

type Colors struct {
	Default  string            `toml:"default"`
	Projects map[string]string `toml:"projects"`
}

type Habits struct {
	Auto []AutoHabit `toml:"auto"`
}

// AutoHabit links a habit to a project and a minimum time (spec 5.8).
type AutoHabit struct {
	Habit   string        `toml:"habit"`
	Project string        `toml:"project"`
	MinRaw  string        `toml:"min"`
	Min     time.Duration `toml:"-"` // parsed from MinRaw
}

// Default returns the configuration used when no file exists; it matches the
// example in spec section 10 (without the user-specific tables).
func Default() Config {
	return Config{
		General:  General{StartPage: "agenda", RefreshSeconds: 60, AgendaDays: 7},
		Adapters: Adapters{Calendar: "khal", Tasks: "taskwarrior", Time: "timewarrior", Habits: "harsh"},
		Calendar: Calendar{Tracked: []string{"plan"}, Blocks: "plan", Writable: []string{"personal", "plan"}},
		Time:     Time{MobileFile: "~/notite/timp-mobil.txt"},
		Notes:    Notes{Dir: "~/notite", Templates: "~/notite/.sabloane", Editor: "hx"},
		Notify:   Notify{MinutesBefore: 10},
		Colors:   Colors{Default: "blue"},
	}
}

// DefaultPath is $XDG_CONFIG_HOME/dashboard/config.toml, falling back to
// ~/.config/dashboard/config.toml.
func DefaultPath() string {
	dir := os.Getenv("XDG_CONFIG_HOME")
	if dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, ".config")
	}
	return filepath.Join(dir, "dashboard", "config.toml")
}

// Load reads the file at path. A missing file is not an error: the defaults
// are returned with a warning.
func Load(path string) (Config, error) {
	cfg := Default()
	data, err := os.ReadFile(path)
	switch {
	case os.IsNotExist(err):
		cfg.Warnings = append(cfg.Warnings, fmt.Sprintf("Configurarea %s lipsește; se folosesc valorile implicite", path))
	case err != nil:
		return cfg, fmt.Errorf("citirea configurării: %w", err)
	default:
		// Decoding into a struct already filled with defaults keeps every
		// default the file does not override.
		md, err := toml.Decode(string(data), &cfg)
		if err != nil {
			return cfg, fmt.Errorf("configurare invalidă (%s): %w", path, err)
		}
		cfg.Path = path
		for _, k := range md.Undecoded() {
			cfg.Warnings = append(cfg.Warnings, fmt.Sprintf("Cheie necunoscută în configurare: %s", k))
		}
	}
	cfg.finish()
	return cfg, nil
}

// finish validates the loaded values, applies fallbacks, expands "~" in paths
// and computes derived fields.
func (c *Config) finish() {
	warn := func(format string, a ...any) { c.Warnings = append(c.Warnings, fmt.Sprintf(format, a...)) }
	def := Default()

	if !slices.Contains(Pages, c.General.StartPage) {
		warn("start_page invalid: %q (valori: %s)", c.General.StartPage, strings.Join(Pages, ", "))
		c.General.StartPage = def.General.StartPage
	}
	if c.General.RefreshSeconds <= 0 {
		warn("refresh_seconds trebuie să fie pozitiv; se folosește %d", def.General.RefreshSeconds)
		c.General.RefreshSeconds = def.General.RefreshSeconds
	}
	if c.General.AgendaDays <= 0 {
		warn("agenda_days trebuie să fie pozitiv; se folosește %d", def.General.AgendaDays)
		c.General.AgendaDays = def.General.AgendaDays
	}

	c.Time.MobileFile = ExpandHome(c.Time.MobileFile)
	c.Notes.Dir = ExpandHome(c.Notes.Dir)
	c.Notes.Templates = ExpandHome(c.Notes.Templates)

	// Colours (spec 5.9): an invalid value is reported and the project falls
	// back to the default colour.
	defColor, err := core.NormalizeColor(c.Colors.Default)
	if err != nil {
		warn("Culoarea implicită: %v; se folosește %q", err, def.Colors.Default)
		defColor, _ = core.NormalizeColor(def.Colors.Default)
	}
	c.Palette = core.Palette{Default: defColor, Projects: map[string]string{}}
	for project, value := range c.Colors.Projects {
		norm, err := core.NormalizeColor(value)
		if err != nil {
			warn("Culoarea proiectului %s: %v; se folosește culoarea implicită", project, err)
			continue
		}
		c.Palette.Projects[project] = norm
	}

	// Automatic habits (spec 5.8): entries with a bad duration are dropped.
	valid := c.Habits.Auto[:0]
	for _, a := range c.Habits.Auto {
		d, err := time.ParseDuration(a.MinRaw)
		if err != nil || d <= 0 || a.Habit == "" || a.Project == "" {
			warn("habits.auto ignorat (obicei %q, proiect %q, min %q)", a.Habit, a.Project, a.MinRaw)
			continue
		}
		a.Min = d
		valid = append(valid, a)
	}
	c.Habits.Auto = valid
}

// ExpandHome replaces a leading "~" with the user's home directory.
func ExpandHome(p string) string {
	if p == "~" || strings.HasPrefix(p, "~/") {
		if home, err := os.UserHomeDir(); err == nil {
			return filepath.Join(home, strings.TrimPrefix(p, "~"))
		}
	}
	return p
}
