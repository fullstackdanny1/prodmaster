// Package notes is screen 4: the list of Markdown notes with a preview
// (spec 6.8). In stage 1 it is a placeholder; it is built in stage 5.
package notes

import "github.com/fullstackdanny1/prodmaster/internal/ui/common"

// New returns the Notes screen.
func New() common.Page {
	return common.NewPlaceholder("Notițe", 5, []string{
		"fișierele din directorul de notițe, cu căutare fuzzy",
		"previzualizarea Markdown a notiței selectate",
		"deschiderea în editorul extern (Enter)",
		"notițe noi din șabloane (N)",
	}, []common.Hint{
		{Key: "Enter", Desc: "deschide în editor", Stage: 5},
		{Key: "N", Desc: "notiță nouă", Stage: 5},
	})
}
