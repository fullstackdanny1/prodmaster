// Package ui is the terminal interface, built with Bubble Tea.
//
// Bubble Tea follows the Elm architecture: the whole UI state lives in one
// value (Model); Update receives a message (a key press, a timer tick, the
// result of a background command) and returns the new state plus, optionally,
// a command to run; View turns the state into a string. Nothing else mutates
// the state, which keeps the flow easy to follow and to test.
//
// The root Model owns what is always on screen (tab bar with the running
// timer, bottom bar, Space menu, help) and the global shortcuts (spec 6.2).
// Everything else is delegated to the active Page.
package ui

import (
	"fmt"
	"slices"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"

	"github.com/fullstackdanny1/prodmaster/internal/config"
	"github.com/fullstackdanny1/prodmaster/internal/core"
	"github.com/fullstackdanny1/prodmaster/internal/ports"
	"github.com/fullstackdanny1/prodmaster/internal/ui/agenda"
	"github.com/fullstackdanny1/prodmaster/internal/ui/common"
	"github.com/fullstackdanny1/prodmaster/internal/ui/notes"
	"github.com/fullstackdanny1/prodmaster/internal/ui/tasks"
	timeview "github.com/fullstackdanny1/prodmaster/internal/ui/time"
)

// Deps are the adapters the UI works with. A nil field means the adapter is
// not available (not configured, not implemented yet or broken); the screens
// that need it show an error, the others keep working (spec 9.4).
type Deps struct {
	Clock    core.Clock
	Calendar ports.Calendar
	Tasks    ports.Tasks
	Time     ports.TimeTracker
	Habits   ports.Habits
	Notes    ports.Notes
	Editor   ports.Editor
	Notifier ports.Notifier
}

// overlay says which popup, if any, is drawn over the content.
type overlay int

const (
	overlayNone overlay = iota
	overlayMenu
	overlayHelp
)

// statusLevel colours the message in the bottom bar.
type statusLevel int

const (
	levelInfo statusLevel = iota
	levelWarn
	levelError
)

// Model is the root state of the application.
type Model struct {
	cfg  config.Config
	deps Deps

	pages  []common.Page
	active int // index into pages

	width, height int
	now           time.Time       // updated every second, drives the timer display
	timer         *core.TimeEntry // running interval, nil if none
	overlay       overlay

	status      string
	statusLevel statusLevel
}

// Messages produced by commands.
type (
	tickMsg    time.Time // once per second
	refreshMsg struct{}  // periodic data reload (refresh_seconds)
	timerMsg   struct {  // result of reading the running interval
		entry *core.TimeEntry
		err   error
	}
)

// New builds the root model. startPage is one of config.Pages; warnings
// (from the configuration and the adapter wiring) are shown in the bottom bar.
func New(cfg config.Config, deps Deps, startPage string, warnings []string) Model {
	if deps.Clock == nil {
		deps.Clock = core.SystemClock{}
	}
	m := Model{
		cfg:  cfg,
		deps: deps,
		// The order matches the tab numbers and config.Pages.
		pages: []common.Page{agenda.New(), tasks.New(), timeview.New(), notes.New()},
		now:   deps.Clock.Now(),
	}
	if i := slices.Index(config.Pages, startPage); i >= 0 {
		m.active = i
	}
	if len(warnings) > 0 {
		m.setStatus(levelWarn, strings.Join(warnings, " · "))
	}
	return m
}

// Init starts the per-second tick, the periodic refresh and the first load.
func (m Model) Init() tea.Cmd {
	return tea.Batch(tick(), m.scheduleRefresh(), m.loadTimer())
}

func tick() tea.Cmd {
	return tea.Tick(time.Second, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m Model) scheduleRefresh() tea.Cmd {
	d := time.Duration(m.cfg.General.RefreshSeconds) * time.Second
	return tea.Tick(d, func(time.Time) tea.Msg { return refreshMsg{} })
}

// loadTimer reads the running interval in the background. It returns nil (no
// command) when there is no time adapter.
func (m Model) loadTimer() tea.Cmd {
	tracker := m.deps.Time
	if tracker == nil {
		return nil
	}
	return func() tea.Msg {
		e, err := tracker.Active()
		return timerMsg{entry: e, err: err}
	}
}

// reload is what happens on start-up, on page change, after a write and
// periodically (spec 9.6). In stage 1 only the timer is loaded; each page
// will add its own data loading as it is implemented.
func (m Model) reload() tea.Cmd { return m.loadTimer() }

func (m *Model) setStatus(level statusLevel, text string) {
	m.status, m.statusLevel = text, level
}

// Update handles one message and returns the new state.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		return m, nil

	case tickMsg:
		m.now = m.deps.Clock.Now()
		return m, tick()

	case refreshMsg:
		return m, tea.Batch(m.reload(), m.scheduleRefresh())

	case timerMsg:
		if msg.err != nil {
			m.setStatus(levelError, "Cronometru: "+msg.err.Error())
			return m, nil
		}
		m.timer = msg.entry
		return m, nil

	case tea.KeyMsg:
		return m.handleKey(msg)
	}

	// Anything else belongs to the active page.
	return m.updatePage(msg)
}

func (m Model) updatePage(msg tea.Msg) (tea.Model, tea.Cmd) {
	page, cmd := m.pages[m.active].Update(msg)
	m.pages[m.active] = page
	return m, cmd
}

func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := msg.String()

	// A message in the bottom bar stays until the next key press.
	m.status = ""

	if key == "ctrl+c" {
		return m, tea.Quit
	}

	switch m.overlay {
	case overlayHelp:
		if key == "esc" || key == "?" || key == "q" {
			m.overlay = overlayNone
		}
		return m, nil
	case overlayMenu:
		m.overlay = overlayNone
		if key == "esc" {
			return m, nil
		}
		if i := slices.IndexFunc(menuItems, func(it menuItem) bool { return it.Key == key }); i >= 0 {
			return m.runMenuItem(menuItems[i])
		}
		return m, nil
	}

	switch key {
	case "q":
		return m, tea.Quit
	case "1", "2", "3", "4":
		return m.switchTo(int(key[0] - '1'))
	case "tab":
		return m.switchTo((m.active + 1) % len(m.pages))
	case "shift+tab":
		return m.switchTo((m.active + len(m.pages) - 1) % len(m.pages))
	case " ":
		m.overlay = overlayMenu
		return m, nil
	case "?":
		m.overlay = overlayHelp
		return m, nil
	}

	// Global actions that are not implemented yet report their stage.
	if i := slices.IndexFunc(globalHints, func(h common.Hint) bool { return h.Key == key && h.Stage > 0 }); i >= 0 {
		m.notYet(globalHints[i])
		return m, nil
	}

	// Page shortcuts that are not implemented yet report their stage too.
	for _, h := range m.pages[m.active].Hints() {
		if h.Key == key && h.Stage > 0 {
			m.notYet(h)
			return m, nil
		}
	}
	return m.updatePage(msg)
}

func (m *Model) notYet(h common.Hint) {
	m.setStatus(levelInfo, fmt.Sprintf("„%s” vine în etapa %d", h.Desc, h.Stage))
}

func (m Model) switchTo(i int) (tea.Model, tea.Cmd) {
	if i == m.active {
		return m, nil
	}
	m.active = i
	return m, m.reload()
}

func (m Model) runMenuItem(it menuItem) (tea.Model, tea.Cmd) {
	// Every menu action belongs to a later stage (spec 6.3, 13).
	m.notYet(common.Hint{Key: it.Key, Desc: it.Desc, Stage: it.Stage})
	return m, nil
}

// ---------------------------------------------------------------- View

// Fallback size before the terminal reports its real size.
const (
	defaultWidth  = 80
	defaultHeight = 24
)

// View draws: tab bar, separator, content, separator, bottom bar.
func (m Model) View() string {
	w, h := m.width, m.height
	if w <= 0 || h <= 0 {
		w, h = defaultWidth, defaultHeight
	}
	bodyHeight := max(h-4, 1)

	sep := common.Separator.Render(strings.Repeat("─", w))
	body := m.pages[m.active].View(w, bodyHeight)
	body = lipgloss.NewStyle().Width(w).Height(bodyHeight).MaxWidth(w).MaxHeight(bodyHeight).Render(body)

	switch m.overlay {
	case overlayMenu:
		popup := m.menuView()
		pw, ph := lipgloss.Width(popup), lipgloss.Height(popup)
		// Bottom-right corner, like Helix.
		body = common.Overlay(body, popup, max(w-pw-1, 0), max(bodyHeight-ph, 0))
	case overlayHelp:
		popup := m.helpView(bodyHeight)
		pw, ph := lipgloss.Width(popup), lipgloss.Height(popup)
		body = common.Overlay(body, popup, max((w-pw)/2, 0), max((bodyHeight-ph)/2, 0))
	}

	return strings.Join([]string{m.topBar(w), sep, body, sep, m.bottomBar(w)}, "\n")
}

// topBar shows the tabs on the left and the running timer on the right.
func (m Model) topBar(w int) string {
	var tabs []string
	for i, p := range m.pages {
		label := fmt.Sprintf(" %d %s ", i+1, p.Title())
		if i == m.active {
			tabs = append(tabs, common.TabActive.Render(label))
		} else {
			tabs = append(tabs, common.TabIdle.Render(label))
		}
	}
	left := strings.Join(tabs, " ")

	right := ""
	if m.timer != nil {
		project := core.EntryProject(*m.timer)
		right = common.ProjectStyle(m.cfg.Palette, project).
			Render(fmt.Sprintf("⏱ %s  %s ", project, common.FormatClock(m.now.Sub(m.timer.Start))))
	}
	return joinEnds(left, right, w)
}

// bottomBar shows the status message if there is one, otherwise the
// shortcuts of the current screen followed by the always-useful ones.
func (m Model) bottomBar(w int) string {
	if m.status != "" {
		style := common.Info
		switch m.statusLevel {
		case levelWarn:
			style = common.Warn
		case levelError:
			style = common.Error
		}
		return style.Render(ansi.Truncate(" "+m.status, w, "…"))
	}
	hints := append(slices.Clone(m.pages[m.active].Hints()),
		common.Hint{Key: "Space", Desc: "meniu"},
		common.Hint{Key: "?", Desc: "ajutor"},
		common.Hint{Key: "q", Desc: "ieșire"},
	)
	var parts []string
	for _, h := range hints {
		parts = append(parts, renderHint(h))
	}
	return ansi.Truncate(" "+strings.Join(parts, "  "), w, "…")
}

func renderHint(h common.Hint) string {
	if h.Stage > 0 {
		return common.Dim.Render(h.Key + " " + h.Desc)
	}
	return common.Key.Render(h.Key) + " " + h.Desc
}

// joinEnds places left and right at the two ends of a line of width w. If they
// do not fit, the left part is truncated.
func joinEnds(left, right string, w int) string {
	rw := lipgloss.Width(right)
	left = ansi.Truncate(left, max(w-rw-1, 0), "…")
	gap := max(w-lipgloss.Width(left)-rw, 0)
	return left + strings.Repeat(" ", gap) + right
}
