// Package common holds what every screen shares: the Page interface, styles,
// formatting helpers and the overlay used for popups.
package common

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// Hint is one shortcut shown in the bottom bar and in the help popup.
// Stage > 0 marks a shortcut whose action arrives in that implementation
// stage (spec 13); it is shown dimmed until then.
type Hint struct {
	Key   string
	Desc  string
	Stage int
}

// Page is one of the four screens (Agendă, Sarcini, Timp, Notițe).
//
// The root model (package ui) owns the tab bar, the bottom bar and the global
// shortcuts. Every message it does not handle itself is forwarded to the
// active page through Update. View receives the exact size of the content area.
type Page interface {
	Title() string
	Update(msg tea.Msg) (Page, tea.Cmd)
	View(width, height int) string
	Hints() []Hint
}

// Placeholder is a page whose real content arrives in a later stage. It shows
// what the screen will contain so the skeleton is self-explanatory.
type Placeholder struct {
	title string
	stage int
	plan  []string
	hints []Hint
}

// NewPlaceholder builds a placeholder page.
func NewPlaceholder(title string, stage int, plan []string, hints []Hint) *Placeholder {
	return &Placeholder{title: title, stage: stage, plan: plan, hints: hints}
}

func (p *Placeholder) Title() string                  { return p.title }
func (p *Placeholder) Update(tea.Msg) (Page, tea.Cmd) { return p, nil }
func (p *Placeholder) Hints() []Hint                  { return p.hints }

func (p *Placeholder) View(width, height int) string {
	var b strings.Builder
	b.WriteString(Title.Render(p.title))
	b.WriteString("\n\n")
	b.WriteString(Dim.Render(fmt.Sprintf("Acest ecran se implementează în etapa %d. Va conține:", p.stage)))
	b.WriteString("\n\n")
	for _, line := range p.plan {
		b.WriteString("  • " + line + "\n")
	}
	// Pad every line to the same width first: Place centres each line on its
	// own, so equal widths keep the text left-aligned inside a centred block.
	text := strings.TrimRight(b.String(), "\n")
	block := lipgloss.NewStyle().Width(lipgloss.Width(text)).Render(text)
	return lipgloss.Place(width, height, lipgloss.Center, lipgloss.Center, block)
}
