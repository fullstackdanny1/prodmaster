package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"

	"github.com/fullstackdanny1/prodmaster/internal/ui/common"
)

// globalHints lists the global shortcuts of spec 6.2. It is the single source
// for the help popup and for the "comes in stage N" messages. Stage 0 means
// the shortcut already works.
var globalHints = []common.Hint{
	{Key: "1–4", Desc: "schimbă ecranul"},
	{Key: "Tab", Desc: "ecranul următor"},
	{Key: "Shift+Tab", Desc: "ecranul anterior"},
	{Key: "Space", Desc: "meniul de acțiuni"},
	{Key: "a", Desc: "adaugă sarcină", Stage: 2},
	{Key: "c", Desc: "captură în inbox", Stage: 5},
	{Key: "s", Desc: "pornește / oprește cronometrul", Stage: 2},
	{Key: "t", Desc: "adaugă timp manual", Stage: 4},
	{Key: "/", Desc: "caută în ecranul curent", Stage: 2},
	{Key: "?", Desc: "ajutor"},
	{Key: "q", Desc: "ieșire"},
}

// navigationHints are the vim-style movement keys (spec 6.1). They are
// handled by the screens, so they become active together with them.
var navigationHints = []common.Hint{
	{Key: "j / k ↓ ↑", Desc: "mișcare", Stage: 2},
	{Key: "Enter / →", Desc: "intră în detalii", Stage: 2},
	{Key: "Esc / ←", Desc: "iese", Stage: 2},
}

// menuItem is an entry of the Space menu (spec 6.3).
type menuItem struct {
	Key, Desc string
	Stage     int
}

var menuItems = []menuItem{
	{"a", "adaugă sarcină", 2},
	{"o", "obiectiv nou", 2},
	{"d", "sarcină cu durată", 2},
	{"b", "bloc de lucru", 3},
	{"c", "captură în inbox", 5},
	{"j", "jurnalul zilei", 5},
	{"t", "adaugă timp manual", 4},
	{"r", "revizuire săptămânală", 6},
}

// menuView renders the Space menu popup.
func (m Model) menuView() string {
	var lines []string
	for _, it := range menuItems {
		line := common.Key.Render(it.Key) + "  " + it.Desc
		if it.Stage > 0 {
			line = common.Dim.Render(it.Key + "  " + it.Desc)
		}
		lines = append(lines, line)
	}
	return popupWithTitle("Acțiuni", strings.Join(lines, "\n"))
}

// helpView renders the help popup: global shortcuts, navigation and the
// shortcuts of the current screen. It is clipped to maxHeight lines.
func (m Model) helpView(maxHeight int) string {
	var b strings.Builder
	section := func(title string, hints []common.Hint) {
		if len(hints) == 0 {
			return
		}
		b.WriteString(common.Title.Render(title) + "\n")
		for _, h := range hints {
			line := fmt.Sprintf("  %-12s %s", h.Key, h.Desc)
			if h.Stage > 0 {
				line = common.Dim.Render(fmt.Sprintf("%s  (etapa %d)", line, h.Stage))
			}
			b.WriteString(line + "\n")
		}
		b.WriteString("\n")
	}
	section("Globale", globalHints)
	section("Navigare", navigationHints)
	section("Ecranul "+m.pages[m.active].Title(), m.pages[m.active].Hints())
	b.WriteString(common.Dim.Render("Esc sau ? închide. Tastele estompate vin în etapele următoare."))

	content := b.String()
	// 2 lines of border.
	if lines := strings.Split(content, "\n"); len(lines) > maxHeight-2 && maxHeight > 2 {
		content = strings.Join(lines[:maxHeight-2], "\n")
	}
	return popupWithTitle("Ajutor", content)
}

// popupWithTitle draws a rounded box with the title embedded in the top
// border: "╭ Titlu ─────╮".
func popupWithTitle(title, content string) string {
	box := common.Popup.Render(content)
	lines := strings.Split(box, "\n")
	w := lipgloss.Width(lines[0])
	label := " " + title + " "
	if lipgloss.Width(label)+3 <= w {
		lines[0] = "╭─" + common.Title.Render(label) + strings.Repeat("─", w-lipgloss.Width(label)-3) + "╮"
	}
	return strings.Join(lines, "\n")
}
