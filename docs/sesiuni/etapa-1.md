# Rezumatul sesiunii: Etapa 1 (Fundația)

Data: 2026-10-06
Branch: `claude/productivity-dashboard-tui-j6f74s`

## Ce s-a făcut

Toate punctele din etapa 1 (specificația, secțiunea 13) sunt implementate și au teste.

| Punct din specificație | Unde | Teste |
|---|---|---|
| Structura proiectului (9.2) | `cmd/`, `internal/{core,ports,adapters,config,ui}` | — |
| Modelul de date (4.2) | `internal/core/model.go` | — (doar tipuri) |
| Ceasul injectat (5) | `internal/core/clock.go` | `core_test.go` |
| Culorile proiectelor (5.9) | `internal/core/color.go`, validare în `config` | `core_test.go`, `config_test.go` |
| Configurarea (10) | `internal/config/config.go`, `config.example.toml` | `config_test.go` |
| Interfețele (9.3) | `internal/ports/ports.go` | — |
| Adaptoarele `fake` | `internal/adapters/fake/` | testele de contract |
| Testele de contract (12) | `internal/ports/contract/` | rulate pe `fake` |
| Schelet UI cu taburi (6.1) | `internal/ui/app.go`, ecranele din `internal/ui/*/` | `app_test.go` |
| Bara de sus cu cronometrul activ (6.1, 9.6) | `Model.topBar` | `TestTimerInTopBar` |
| Bara de jos: scurtături și mesaje (6.1) | `Model.bottomBar` | `TestWarningsShownAtStart` |
| Meniul `Space` (6.3) | `internal/ui/keys.go` | `TestSpaceMenu` |
| Ajutorul `?` (6.2) | `internal/ui/keys.go` | `TestHelp` |
| Linia de comandă (9.5) | `cmd/dashboard/main.go` | `main_test.go` |

Comportamente verificate și manual, în terminal (tmux, 100×24 și 100×30): taburile, meniul `Space` în colțul din dreapta jos, ajutorul centrat, avertismentele de configurare în bara de jos, mesajul „vine în etapa N”.

`go vet ./...` și `go test ./...` trec.

## Ce a rămas (etapele următoare)

- **Etapa 2:** adaptoarele Taskwarrior și Timewarrior; ecranul Sarcini; cronometrul (`s`); adăugarea (`a`).
- **Etapa 3:** adaptorul khal; ecranul Agendă; blocurile și împrumutul de subtask-uri.
- **Etapa 4:** ecranul Timp; timpul manual; importul de pe telefon; `dashboard import-timp`.
- **Etapa 5:** notițele, editorul, șabloanele, jurnalul; `dashboard jurnal`.
- **Etapa 6:** harsh, rutinele, obiectivele la final de perioadă, revizuirea săptămânală, `dashboard notify`.

În mediul acestei sesiuni nu sunt instalate `task`, `timew`, `khal`, `harsh` și `hx`. Pentru etapa 2 trebuie verificat formatul exact al ieșirii lui `task export` și `timew export` pe versiunile instalate (specificația, 14). Fie le instalez în mediul de lucru, fie îmi trimiteți ieșirea de pe sistemul dumneavoastră.

## Abateri și adăugiri față de specificație

1. **Adaptorul `"fake"` poate fi ales din configurare.** Specificația prevede adaptoarele fake doar pentru teste. Le-am făcut selectabile în `[adapters]` ca să se poată încerca interfața fără unelte. Nu adaugă funcționalitate nouă, doar refolosește codul de test. Se poate scoate dacă nu e dorit.
2. **Adaptoarele reale neimplementate încă** lasă portul gol. Bara de jos afișează `Adaptorul taskwarrior (tasks) vine în etapa 2`. Cu configurarea implicită, aceste avertismente apar la fiecare pornire până la implementarea adaptoarelor.
3. **Chei necunoscute în `config.toml`** produc un avertisment, ca greșelile de scriere să nu treacă neobservate.
4. **Mesajele din bara de jos dispar la următoarea tastă.** Specificația nu spune cât rămân afișate.
5. **Ecranele sunt schițe** care descriu ce vor conține, iar tastele viitoare sunt afișate estompat. Acestea dispar pe măsură ce ecranele se implementează.
6. **`Notes.CreateFromTemplate`:** locația fișierului creat după tip (`prelegere` → `cursuri/<proiect>/…`) nu e fixată încă, deci nu e în testele de contract. Adaptorul fake creează `<tip>/<titlu>.md`. Se stabilește în etapa 5.
7. **Bubble Tea v1** (v1.3.10), versiunea stabilă cunoscută. Biblioteca `x/ansi` e folosită direct (pentru popup-uri) și e fixată la versiunea cerută de Bubble Tea v1.3.10, pentru că versiunile mai noi nu sunt compatibile.
8. **Pachetul `internal/ui/time` se numește `timeview`**, ca să nu intre în conflict cu pachetul standard `time`. Directorul păstrează numele din specificație.

## Întrebări înainte de etapa 2

1. **Sensul lui `depends`.** În Taskwarrior, `A depends:B` înseamnă „A e blocată până se termină B”. Am înțeles că părintele are subtask-urile în `depends` (deci e blocat de ele). Consecințe: părintele apare ca `+BLOCKED`, iar la bifarea unui părinte cu subtask-uri deschise Taskwarrior poate afișa avertismente. Pentru obiective (judecate după rezultat, 4.5) e în regulă? Formularea din 4.4, „prin `depends` pe părinte”, se poate citi și invers (subtask-ul depinde de părinte).
2. **Proiectul cronometrului activ.** Hook-ul `on-modify.timewarrior` pune pe interval descrierea sarcinii, proiectul și tag-urile, fără o ordine garantată. Deocamdată iau primul tag care arată ca un nume de proiect (litere mici, cifre, cratime, puncte; `core.EntryProject`). Alternativa ar fi să caut tag-ul printre proiectele cunoscute din Taskwarrior. Care variantă o preferați?
3. **`include_subprojects`** (5.1): când e `true`, tag-ul `y` include și `y.import`. Se aplică și în sens invers? De exemplu, o sarcină cu durată pe `y.import` nu numără timpul de pe `y`.
4. Pot instala Taskwarrior 3.x și Timewarrior în mediul de lucru, pentru testele de integrare? Sau preferați să-mi trimiteți ieșirea `task export` și `timew export` de pe sistemul dumneavoastră?
