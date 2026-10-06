package ui

import (
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"

	"github.com/fullstackdanny1/prodmaster/internal/adapters/fake"
	"github.com/fullstackdanny1/prodmaster/internal/config"
	"github.com/fullstackdanny1/prodmaster/internal/core"
)

var t0 = time.Date(2026, 10, 6, 9, 0, 0, 0, time.Local)

func newModel(t *testing.T) (Model, *core.FixedClock, *fake.TimeTracker) {
	t.Helper()
	clock := &core.FixedClock{T: t0}
	tracker := fake.NewTimeTracker(clock)
	cfg := config.Default()
	cfg.Palette = core.Palette{Default: "4", Projects: map[string]string{}}
	m := New(cfg, Deps{Clock: clock, Time: tracker}, "agenda", nil)
	m = send(t, m, tea.WindowSizeMsg{Width: 100, Height: 30})
	return m, clock, tracker
}

// send runs one message through Update.
func send(t *testing.T, m Model, msg tea.Msg) Model {
	t.Helper()
	next, _ := m.Update(msg)
	return next.(Model)
}

func key(s string) tea.KeyMsg {
	switch s {
	case "tab":
		return tea.KeyMsg{Type: tea.KeyTab}
	case "shift+tab":
		return tea.KeyMsg{Type: tea.KeyShiftTab}
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEsc}
	case " ":
		return tea.KeyMsg{Type: tea.KeySpace, Runes: []rune(" ")}
	}
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

func plain(m Model) string { return ansi.Strip(m.View()) }

func TestTabsAndSwitching(t *testing.T) {
	m, _, _ := newModel(t)
	v := plain(m)
	for _, tab := range []string{"1 Agendă", "2 Sarcini", "3 Timp", "4 Notițe"} {
		if !strings.Contains(v, tab) {
			t.Errorf("tab %q missing", tab)
		}
	}
	m = send(t, m, key("3"))
	if m.active != 2 {
		t.Errorf("after 3: active = %d", m.active)
	}
	m = send(t, m, key("tab"))
	if m.active != 3 {
		t.Errorf("after tab: active = %d", m.active)
	}
	m = send(t, m, key("tab"))
	if m.active != 0 {
		t.Errorf("tab should wrap around, active = %d", m.active)
	}
	m = send(t, m, key("shift+tab"))
	if m.active != 3 {
		t.Errorf("shift+tab should wrap around, active = %d", m.active)
	}
}

func TestStartPage(t *testing.T) {
	m := New(config.Default(), Deps{}, "timp", nil)
	if m.active != 2 {
		t.Errorf("active = %d, want 2", m.active)
	}
}

func TestSpaceMenu(t *testing.T) {
	m, _, _ := newModel(t)
	m = send(t, m, key(" "))
	if m.overlay != overlayMenu {
		t.Fatal("menu not open")
	}
	v := plain(m)
	for _, s := range []string{"Acțiuni", "obiectiv nou", "revizuire săptămânală"} {
		if !strings.Contains(v, s) {
			t.Errorf("menu does not show %q", s)
		}
	}
	// Choosing an item closes the menu and reports the stage.
	m = send(t, m, key("r"))
	if m.overlay != overlayNone {
		t.Error("menu still open")
	}
	if !strings.Contains(m.status, "etapa 6") {
		t.Errorf("status = %q", m.status)
	}
	// Esc closes without action.
	m = send(t, m, key(" "))
	m = send(t, m, key("esc"))
	if m.overlay != overlayNone || m.status != "" {
		t.Errorf("overlay = %v, status = %q", m.overlay, m.status)
	}
}

func TestHelp(t *testing.T) {
	m, _, _ := newModel(t)
	m = send(t, m, key("?"))
	v := plain(m)
	for _, s := range []string{"Ajutor", "Globale", "captură în inbox", "Ecranul Agendă"} {
		if !strings.Contains(v, s) {
			t.Errorf("help does not show %q", s)
		}
	}
	// q closes the help instead of quitting.
	next, cmd := m.Update(key("q"))
	m = next.(Model)
	if m.overlay != overlayNone || cmd != nil {
		t.Error("q in help should only close it")
	}
}

func TestQuit(t *testing.T) {
	m, _, _ := newModel(t)
	_, cmd := m.Update(key("q"))
	if cmd == nil {
		t.Fatal("no command")
	}
	if _, ok := cmd().(tea.QuitMsg); !ok {
		t.Error("q does not quit")
	}
}

func TestUnimplementedShortcutReportsStage(t *testing.T) {
	m, _, _ := newModel(t)
	m = send(t, m, key("a"))
	if !strings.Contains(m.status, "adaugă sarcină") || !strings.Contains(m.status, "etapa 2") {
		t.Errorf("status = %q", m.status)
	}
	// Status disappears at the next key press.
	m = send(t, m, key("2"))
	if m.status != "" {
		t.Errorf("status not cleared: %q", m.status)
	}
}

func TestWarningsShownAtStart(t *testing.T) {
	m := New(config.Default(), Deps{}, "agenda", []string{"culoare invalidă"})
	if !strings.Contains(ansi.Strip(m.View()), "culoare invalidă") {
		t.Error("warning not shown in the bottom bar")
	}
}

func TestTimerInTopBar(t *testing.T) {
	m, clock, tracker := newModel(t)
	if strings.Contains(plain(m), "⏱") {
		t.Fatal("timer shown while none is running")
	}
	if err := tracker.Start("Tema 2", "ia"); err != nil {
		t.Fatal(err)
	}
	// Simulate the reload, then 42 minutes of ticks.
	m = send(t, m, m.loadTimer()())
	clock.Advance(42 * time.Minute)
	m = send(t, m, tickMsg(clock.Now()))
	if v := plain(m); !strings.Contains(v, "⏱ ia  0:42") {
		t.Errorf("top bar = %q", strings.SplitN(v, "\n", 2)[0])
	}
}
