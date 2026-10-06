// Package tasks is screen 2: objectives, routines and tasks grouped by horizon
// (spec 6.6). In stage 1 it is a placeholder; it is built in stage 2.
package tasks

import "github.com/fullstackdanny1/prodmaster/internal/ui/common"

// New returns the Tasks screen.
func New() common.Page {
	return common.NewPlaceholder("Sarcini", 2, []string{
		"Obiective și Rutine azi",
		"sarcinile grupate pe orizont: Azi, Săptămâna asta, Luna asta, Mai târziu, Fără termen",
		"subtask-urile indentate sub părinte, pliabile",
		"progresul sarcinilor cu durată",
	}, []common.Hint{
		{Key: "x", Desc: "bifează", Stage: 2},
		{Key: "A", Desc: "subtask", Stage: 2},
		{Key: "e", Desc: "modifică", Stage: 2},
		{Key: "D", Desc: "șterge", Stage: 2},
		{Key: "n", Desc: "notiță", Stage: 5},
	})
}
