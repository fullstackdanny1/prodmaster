# Specificație: dashboard de productivitate (TUI)

> Document de referință pentru dezvoltare asistată de AI.
> Se citește integral înainte de orice sesiune de lucru. Tot ce nu apare aici nu se implementează fără acordul autorului.

---

## 1. Scop

O aplicație TUI care oferă o **vedere unică** asupra timpului, sarcinilor, calendarului, obiceiurilor și notițelor, pentru un sistem Linux cu Sway.

Aplicația este un **strat subțire peste unelte existente**. Ea nu deține date proprii: citește și scrie prin uneltele dedicate (khal, Taskwarrior, Timewarrior, harsh, fișiere Markdown) și adaugă doar ce le lipsește acestora: vederea unificată, legăturile dintre ele și regulile de mai jos.

---

## 2. Principii (obligatorii)

1. **Doar productivitate.** Ce nu ajută direct la planificat, lucrat sau învățat nu intră în aplicație. Finanțele, de exemplu, sunt explicit excluse.
2. **Fără bază de date proprie.** Datele stau în uneltele externe. Aplicația are doar fișierul de configurare.
3. **Modularitate prin porturi și adaptoare.** Nucleul nu cunoaște nicio unealtă. Orice unealtă poate fi înlocuită scriind un adaptor nou.
4. **Regulile stau în nucleu.** Progresul, orizonturile, evaluarea blocurilor și împrumutul de subtask-uri sunt logică de nucleu, nu de adaptor.
5. **Notițele se editează în editorul extern** (Helix implicit). Aplicația doar listează, previzualizează, creează din șabloane și deschide editorul.
6. **Cronometrul nu pornește niciodată automat.** Aplicația poate sugera, dar utilizatorul decide.
7. **Cronometrarea este pentru munca la laptop.** Activitățile făcute în mod obișnuit departe de laptop se urmăresc ca obiceiuri, nu prin timp.
8. **Minimalism.** O singură implementare per interfață la început. Nicio funcție „pentru mai târziu” fără să fie cerută.

---

## 3. Unelte externe

| Rol | Unealtă | Observații |
|---|---|---|
| Calendar | **khal** | Calendarele sunt directoare `.ics` |
| Sincronizare calendar | **vdirsyncer** | Google se citește prin adresa iCal secretă (doar citire). Aplicația **nu** sincronizează nimic singură |
| Sarcini, obiective | **Taskwarrior 3.x** | Se folosesc UUID-uri, niciodată ID-uri numerice |
| Timp | **Timewarrior** | Hook-ul `on-modify.timewarrior` instalat |
| Obiceiuri | **harsh** | Fișiere text în `~/.config/harsh/` (sau `$HARSHPATH`) |
| Notițe | fișiere Markdown în `~/notite/` | Versionate cu git de utilizator |
| Editor | **Helix** (`hx`) | Configurabil |
| Notificări | `notify-send` (mako) | |

### Configurare necesară în `~/.taskrc`

```
weekstart=monday

uda.durata.type=duration
uda.durata.label=Durată

uda.orizont.type=string
uda.orizont.values=zi,saptamana,luna
uda.orizont.label=Orizont
```

### Calendare khal

| Calendar | Sursă | Scriere | Time tracking |
|---|---|---|---|
| `cursuri` (și alte calendare Google) | Google, prin vdirsyncer | nu | nu |
| `personal` | local | da | nu |
| `plan` | local, blocuri de lucru | da | **da** |

Care calendare sunt urmărite în timp se stabilește în configurare (secțiunea 10).

---

## 4. Modelul de date

Există trei surse: **evenimente** (ce se întâmplă la o oră fixă), **sarcini** (ce lucrezi) și **obiceiuri** (ce repeți). Timpul este măsurat separat și legat prin **proiect**.

### 4.1 Convenția centrală: proiectul

- Proiectul Taskwarrior = tag-ul Timewarrior = titlul blocului din calendarul `plan` = folderul de notițe al proiectului sau cursului.
- Pentru evenimentele din Google (titluri lungi), corespondența titlu → proiect se face printr-un tabel în configurare. Dacă un titlu nu are corespondență, evenimentul nu are proiect asociat.
- Numele de proiect: litere mici, cifre, cratime, fără diacritice. Subproiectele folosesc punctul (`y.import`).

### 4.2 Tipuri

| Tip | Unde stă | Cum se recunoaște | Se termină când | Timp |
|---|---|---|---|---|
| **Eveniment** | khal (`cursuri`, `personal`) | orice eveniment din afara calendarului `plan` | trece ora | nu |
| **Bloc de lucru** | khal (`plan`) | eveniment din calendarul `plan`; titlul = proiect | trece intervalul | da, doar în interval |
| **Sarcină simplă** | Taskwarrior | fără `+obiectiv`, fără `durata` | utilizatorul o bifează | opțional |
| **Obiectiv** | Taskwarrior | tag `+obiectiv` | utilizatorul decide că rezultatul e atins | nu |
| **Sarcină cu durată** | Taskwarrior | are `durata`; necesită `project` și `orizont` | ținta de timp e atinsă (confirmat de utilizator) | da |
| **Subtask** | Taskwarrior | este în lista `depends` a altei sarcini | utilizatorul îl bifează | opțional |
| **Obicei** | harsh | definit în fișierul de obiceiuri | nu se termină; se măsoară consecvența | nu (vezi 5.8) |

Reguli de clasificare, în ordine: dacă are `durata` → sarcină cu durată (chiar dacă are și `+obiectiv`); altfel dacă are `+obiectiv` → obiectiv; altfel sarcină simplă. Un subtask poate fi de orice tip, dar se afișează sub părintele lui, nu în secțiunile de nivel superior.

### 4.3 Orizonturi

Sarcinile se grupează după termen (`due`):

| Secțiune | Condiție |
|---|---|
| Azi | `due` azi sau depășit |
| Săptămâna asta | `due` până la sfârșitul săptămânii curente (luni–duminică) |
| Luna asta | `due` până la sfârșitul lunii curente |
| Mai târziu | `due` după luna curentă |
| Fără termen | fără `due` |

Pentru **sarcinile cu durată**, fereastra de măsurare se stabilește din UDA-ul `orizont`:

| `orizont` | Fereastră | `due` setat automat la creare |
|---|---|---|
| `zi` | ziua curentă | `eod` |
| `saptamana` | luni 00:00 – duminică 23:59 | `eow` |
| `luna` | prima zi 00:00 – ultima zi 23:59 | `eom` |

### 4.4 Subtask-uri și împrumutul lor

- Un subtask aparține **unui singur** părinte (obiectiv, sarcină cu durată sau sarcină simplă), prin `depends` pe părinte.
- **Sarcinile unui curs** sunt sarcini cu `project` = proiectul cursului și `due` = ora de început a evenimentului. Ele se afișează sub eveniment în agendă. Pot fi recurente (`recur:weekly`) și pot fi bifate oricând, inclusiv înainte de curs.
- **Blocurile de lucru nu dețin subtask-uri, ci le împrumută.** Când utilizatorul alege subtask-uri pentru un bloc, aplicația le setează `scheduled` = ora de început a blocului. Sub bloc se afișează subtask-urile din același proiect cu `scheduled` egal cu începutul blocului.
- După sfârșitul unui bloc, subtask-urile împrumutate și nebifate își pierd `scheduled` și primesc adnotarea `lucrat în blocul din AAAA-LL-ZZ`. Ele rămân la părintele lor. Nu se creează niciodată copii.

### 4.5 Obiective

- Au `due` = sfârșitul perioadei și, opțional, `orizont`.
- Se judecă după **rezultat**, nu după subtask-uri. Numărul de subtask-uri bifate este doar informativ.
- Pot avea o notiță de progres `~/notite/obiective/<nume>.md`, legată prin adnotarea sarcinii (calea fișierului).
- **La sfârșitul perioadei** (termen depășit), aplicația cere o decizie: **atins** (bifează), **neatins** (bifează cu adnotarea `neatins`) sau **prelungit** (alegi un termen nou). Apoi, pentru fiecare subtask deschis: **transferă** (către alt obiectiv), **mută** (devine sarcină de nivel superior) sau **renunță** (șterge).

### 4.6 Obiceiuri

- Definite în fișierul harsh, grupate pe titluri (`! Igienă`). Frecvențe: `1` zilnic, `3/7`, `1w`, `2/30` etc.
- O rutină = un grup de obiceiuri. Nu se creează sarcini zilnice pentru rutine.
- Regula de alegere (de afișat în documentația utilizatorului): dacă ratarea lasă ceva de recuperat → sarcină recurentă în Taskwarrior; dacă ratarea doar strică seria → obicei.

---

## 5. Regulile nucleului

Toate calculele folosesc un ceas injectat (interfața `Clock`), pentru testare.

### 5.1 Timp pe proiect într-o fereastră

`timp(proiect, start, end)` = suma suprapunerilor dintre intervalele Timewarrior care au tag-ul `proiect` și fereastra `[start, end]`. Intervalul activ (fără sfârșit) se consideră până la „acum”. Un tag `y` nu include automat subproiectele `y.*`, cu excepția cazului în care configurarea o cere (`include_subprojects = true`).

### 5.2 Evaluarea unui bloc

- `in_bloc` = `timp(proiect, start_bloc, end_bloc)`
- `in_afara` = timpul pe același proiect, în aceeași zi, în afara blocului (afișat separat)
- Progres = `in_bloc / durata_bloc`, afișat ca bară și text (`1h40 / 2h`). Peste 100% este permis și afișat (`2h15 / 2h ✓`).
- Subtask-urile bifate nu influențează evaluarea.

### 5.3 Progresul unei sarcini cu durată

- Progres = `timp(proiect, fereastra_orizontului) / durata`.
- Timpul din blocuri se adună și aici. Aceeași oră contează pentru bloc și pentru sarcina cu durată (măsoară lucruri diferite: programul vs. volumul).
- La atingerea țintei, aplicația afișează o sugestie de bifare. Nu bifează singură.
- La crearea unei a doua sarcini cu durată pe același proiect și același orizont, se afișează un avertisment care recomandă subproiecte.

### 5.4 Cronometrul

- Un singur cronometru activ (limitare Timewarrior). Pornirea altuia îl oprește pe cel curent.
- Pe o sarcină din Taskwarrior: `task <uuid> start` (hook-ul pornește Timewarrior cu tag-urile sarcinii, inclusiv proiectul). Oprirea: `task <uuid> stop`.
- Pe un bloc de lucru: `timew start <proiect>`.
- Pe un eveniment dintr-un calendar fără time tracking: acțiunea nu este disponibilă.

### 5.5 Introducere manuală de timp

- Utilizatorul poate adăuga un interval retroactiv: proiect + (început și sfârșit) sau (durată, terminată acum). Se folosește `timew track`.

### 5.6 Import de timp de pe telefon

- Fișier text configurabil (implicit `~/notite/timp-mobil.txt`), sincronizat de utilizator (de ex. Syncthing).
- Format, câte o intrare pe linie: `AAAA-LL-ZZ HH:MM-HH:MM proiect`. Liniile goale și cele care încep cu `#` se ignoră.
- La pornirea aplicației și în revizuirea săptămânală: fiecare linie validă se importă cu `timew track` și se elimină din fișier. Liniile invalide rămân în fișier și generează un avertisment în bara de stare. Importul este idempotent (o intrare identică deja existentă nu se dublează).

### 5.7 Sarcinile cursurilor

- Sarcinile unui curs nebifate la ora de început a evenimentului sunt evidențiate.

### 5.8 Obiceiuri completate automat din timp (opțional)

- Configurarea poate lega un obicei de un proiect și o durată minimă (`Citit` ↔ `citit`, `30m`).
- Dacă `timp(proiect, ziua)` ≥ minim și obiceiul nu e înregistrat pentru ziua respectivă, aplicația scrie `y` în log-ul harsh.

### 5.9 Culorile proiectelor

- Culorile se definesc **exclusiv în configurare** (secțiunea 10): o culoare implicită și, opțional, culori pentru proiecte anume.
- Un proiect fără culoare proprie primește culoarea implicită.
- Se pot defini culori pentru proiecte care **nu există încă**. Intrarea nu creează proiectul și nu apare în nicio listă, dar în momentul în care proiectul apare (în Taskwarrior sau Timewarrior), primește automat acea culoare.
- Culoarea unui proiect se folosește peste tot unde apare proiectul: graficul din ecranul Timp, eticheta de proiect din liste, cronometrul din bara de sus.
- Valori acceptate: nume de culori de terminal (`green`), indici ANSI 0–255 (`208`) și hex (`#e5a50a`). O valoare invalidă se semnalează în bara de stare la pornire, iar proiectul folosește culoarea implicită.

---

## 6. Interfața

### 6.1 Structură generală

```
 1 Agendă   2 Sarcini   3 Timp   4 Notițe                  ⏱ ia  0:42
──────────────────────────────────────────────────────────────────────
 [conținutul ecranului: listă în stânga, detalii în dreapta]
──────────────────────────────────────────────────────────────────────
 a adaugă  x bifează  s cronometru  Space meniu  ? ajutor
```

- **Bara de sus:** taburile și cronometrul activ (proiect + durată), vizibile mereu.
- **Bara de jos:** scurtăturile relevante pentru ecranul curent și mesajele de stare (avertismente, confirmări).
- Navigare în stil vim: `j`/`k` și săgețile pentru mișcare, `Enter`/`→` intră în detalii, `Esc`/`←` iese.

### 6.2 Scurtături globale

| Tastă | Acțiune |
|---|---|
| `1`–`4` | schimbă ecranul |
| `Tab` / `Shift+Tab` | ecranul următor / anterior |
| `Space` | meniul de acțiuni (stil Helix) |
| `a` | adaugă sarcină (cu proiectul precompletat din context) |
| `c` | captură rapidă în `~/notite/inbox.md` |
| `s` | pornește / oprește cronometrul pe elementul selectat |
| `t` | adaugă timp manual |
| `/` | caută în ecranul curent |
| `?` | ajutor (toate scurtăturile) |
| `q` | ieșire |

### 6.3 Meniul `Space`

Popup cu opțiuni și litera fiecăreia, ca în Helix:

```
 ┌ Acțiuni ──────────────────┐
 │ a  adaugă sarcină         │
 │ o  obiectiv nou           │
 │ d  sarcină cu durată      │
 │ b  bloc de lucru          │
 │ c  captură în inbox       │
 │ j  jurnalul zilei         │
 │ t  adaugă timp manual     │
 │ r  revizuire săptămânală  │
 └───────────────────────────┘
```

### 6.4 Introducerea datelor

- Adăugarea de sarcini folosește un rând de introducere cu **sintaxa Taskwarrior** (`Tema 3 project:ia due:fri`), transmisă ca atare.
- Formularele (bloc, sarcină cu durată, timp manual) sunt câmpuri succesive pe un singur rând sau un mic popup. Fără ferestre complexe.
- Acțiunile distructive (ștergere, renunțare la subtask) cer confirmare.

### 6.5 Ecranul 1: Agendă

```
 Lun 05                                │ Curs Inteligență Artificială
   10:00–12:00  Curs Inteligență Art.  │ 10:00–12:00 · Sala 204
     ☑ Ia notițe                       │
     ☐ Fă tema 2                       │ Sarcini deschise (ia):
 ▶ 14:00–16:00  ▪ proiect-y  1h40 / 2h │   ☐ Citește capitolul 5
     ☑ Schițează arhitectura           │
     ☐ Implementează importul          │ Notiță: cursuri/ia/2026-10-05.md
 Mar 06                                │
   …                                   │
```

- Listă cronologică pe zile, de azi înainte, pe un număr configurabil de zile (implicit 7).
- Conține evenimente și blocuri. Blocurile sunt marcate distinct (`▪`) și au bară de progres.
- Sub fiecare eveniment: sarcinile proprii (cursuri). Sub fiecare bloc: subtask-urile împrumutate.
- Panoul din dreapta: descriere, oră, locație, subtask-uri, sarcinile deschise ale proiectului asociat, notița asociată.
- Acțiuni specifice:
  - `x` bifează subtask-ul selectat;
  - `s` pe un bloc pornește cronometrul;
  - `b` creează bloc (`khal new -a plan …`);
  - `i` (pe un bloc) alege subtask-uri de împrumutat din sarcinile deschise ale proiectului;
  - `n` deschide/creează notița prelegerii `cursuri/<proiect>/AAAA-LL-ZZ.md` din șablon.

### 6.6 Ecranul 2: Sarcini

```
 Obiective
   ◎ Găsește-ți un job               2/5   termen: 31 oct
 Rutine azi                                      seria
   ☑ Dinți dimineața                            12 zile
   ☐ Ață dentară
   ◐ Sală                         1/3 săptămâna asta
 Azi
 ▶ ⏱ Lucrez la proiectul y   y   2h15 / 3h ██████░░
      ☑ Schițează arhitectura
      ☐ Scrie testele
   ☐ Tema 2 – Rețele neuronale    ia
 Săptămâna asta
   …
 Fără termen
   …
```

- Secțiuni, în ordine: **Obiective** (cu termen în perioada curentă), **Rutine azi** (din harsh), apoi orizonturile din 4.3.
- Subtask-urile apar indentate sub părinte și pot fi pliate/desfăcute (`Enter`).
- Simboluri: `☐`/`☑` sarcini, `◎` obiectiv, `⏱` sarcină cu durată, `◐` obicei cu frecvență pe mai multe zile.
- Acțiuni specifice:
  - `x` bifează (sarcină, subtask sau obicei);
  - `A` adaugă subtask la elementul selectat (creează sarcina și setează `depends` pe părinte);
  - `e` modifică (rând de introducere precompletat, aplicat cu `task <uuid> modify`);
  - `D` șterge (cu confirmare);
  - `n` deschide notița asociată (adnotare cu cale `.md`, altfel notița proiectului `proiecte/<proiect>.md`, creată dacă nu există).
- Obiectivele cu termen depășit afișează un marcaj și deschid fluxul de decizie din 4.5 la `Enter`.

### 6.7 Ecranul 3: Timp

```
 Săptămâna asta  ◂ ▸                   │ proiect-y           total 6h40
───────────────────────────────────────│───────────────────────────────
 ▶ ■ proiect-y              6h40       │ Lun  ████████ 2h15
   ■ ia                     4h10       │ Mar  ███ 0h50
   ■ citit                  1h30       │ Mie  ██████ 1h40
   ■ rust                   0h00       │ Joi  ███████ 1h55
                                       │ Vin
                                       │ Sâm
                                       │ Dum
                                       │
                                       │ Planificat 8h · Realizat 6h40
```

- **Stânga: lista proiectelor.** Reuniunea proiectelor din Taskwarrior și a tag-urilor din Timewarrior. Fiecare rând are un marcaj în culoarea proiectului, numele și timpul total în perioada selectată. Lista se ordonează descrescător după timp; proiectele fără timp în perioadă apar la final.
- **Dreapta: graficul proiectului selectat**, desenat integral în culoarea proiectului:

  | Perioadă | Bare |
  |---|---|
  | Săptămâna asta / săptămâna trecută | câte una pe zi |
  | Luna asta / luna trecută | câte una pe zi |
  | Anul acesta | câte una pe lună |

- Sub grafic: timpul total și **plan vs. realitate** pentru proiect în perioada selectată (planificat = blocuri + ținte ale sarcinilor cu durată care cad în perioadă).
- Perioada se schimbă cu `[` și `]` și se aplică atât listei, cât și graficului.
- Acțiuni: `j`/`k` alege proiectul, `t` adaugă timp manual (proiectul selectat precompletat), `s` oprește cronometrul activ, `I` forțează importul din fișierul mobil.

### 6.8 Ecranul 4: Notițe

- Listă de fișiere din `~/notite/` cu căutare fuzzy după nume. `/` caută și în conținut (ripgrep, dacă e disponibil).
- Previzualizare Markdown randată în panoul din dreapta.
- `Enter` deschide fișierul în editor: aplicația se suspendă și revine la ieșirea din editor.
- `N` creează o notiță nouă din șablon (alegi tipul, apoi titlul).
- Fără editare în aplicație.

---

## 7. Notițe

### 7.1 Structură

```
~/notite/
  inbox.md                    ← captură rapidă
  timp-mobil.txt              ← import de timp de pe telefon
  cursuri/<proiect>/
    index.md                  ← programă, termene, linkuri
    AAAA-LL-ZZ.md             ← o notiță pe prelegere
  proiecte/<proiect>.md
  obiective/<nume>.md         ← notițe de progres
  surse/<titlu-scurt>.md      ← cărți, articole, videoclipuri
  subiecte/<subiect>.md       ← idei sintetizate
  jurnal/
    zilnic/AAAA-LL-ZZ.md
    <domeniu>.md              ← jurnale de progres (de ex. sala.md)
  .sabloane/
    prelegere.md  sursa.md  obiectiv.md  jurnal.md  proiect.md
```

- Numele fișierelor: unice în tot arborele, litere mici, cratime, fără diacritice (linkurile `[[nume]]` funcționează fără căi).
- Șabloanele folosesc variabilele `{{titlu}}`, `{{data}}`, `{{proiect}}`.

### 7.2 Jurnalul zilnic

- `Space j` deschide `jurnal/zilnic/<azi>.md`, creându-l din șablon dacă nu există.
- Fișierul conține o secțiune generată între marcaje:

```markdown
<!-- auto:start -->
## Ziua în cifre
- Evenimente: …
- Sarcini terminate: …
- Timp pe proiecte: ia 2h10 · proiect-y 2h15
- Plan vs. realitate: planificat 4h · realizat 4h25
- Obiceiuri: 5/7
<!-- auto:end -->

## Reflecții
```

- La fiecare deschidere, aplicația regenerează **doar** conținutul dintre marcaje. Restul fișierului nu este atins niciodată.

### 7.3 Jurnale de progres

- `jurnal/<domeniu>.md`, cu intrări adăugate la final, cu format constant:

```markdown
## AAAA-LL-ZZ
- element: valoare
- notă: text
```

- Aplicația poate adăuga o intrare nouă din șablon (`Space` → notiță nouă → intrare de progres). Fără grafice în prima versiune.

---

## 8. Revizuirea săptămânală (`Space r`)

Un ecran-ghid cu pași parcurși în ordine; fiecare pas poate fi sărit.

1. **Inbox:** fiecare rând din `inbox.md` → sarcină, notiță nouă sau ștergere.
2. **Timp de pe telefon:** importul din 5.6 și afișarea liniilor invalide.
3. **Obiective încheiate:** fluxul de decizie din 4.5.
4. **Săptămâna trecută:** plan vs. realitate pe proiecte, procentul obiceiurilor.
5. **Săptămâna următoare:** creare rapidă de blocuri și sarcini cu durată.

---

## 9. Arhitectură

### 9.1 Limbaj și biblioteci

- **Go**, cu **Bubble Tea** (UI), **Lip Gloss** (stil), **Bubbles** (componente), **Glamour** (Markdown), o bibliotecă TOML și una de căutare fuzzy.
- Dependențe minime. Fiecare dependență nouă se justifică.
- Codul (identificatori, comentarii, mesaje de commit) în engleză. Textele din interfață în română.

### 9.2 Structura proiectului

```
cmd/dashboard/        ← punct de intrare, parsarea argumentelor
internal/
  core/               ← modelul de date și regulile (secțiunea 5)
  ports/              ← interfețele
  adapters/
    khal/
    taskwarrior/
    timewarrior/
    harsh/
    notes/            ← fișiere Markdown, șabloane, jurnal
    editor/
    notify/
    fake/             ← implementări în memorie pentru teste
  config/
  ui/
    agenda/  tasks/  time/  notes/  review/  common/
```

### 9.3 Interfețe (porturi)

Interfețele descriu modelul aplicației, nu comenzile uneltelor. Semnăturile de mai jos sunt orientative.

```go
type Clock interface { Now() time.Time }

type Calendar interface {
    Events(from, to time.Time) ([]Event, error)
    AddEvent(calendar string, e Event) error   // doar calendare care permit scriere
}

type Tasks interface {
    List(f TaskFilter) ([]Task, error)
    Add(raw string) (Task, error)               // sintaxă Taskwarrior
    Modify(uuid string, raw string) error
    Complete(uuid string) error
    Delete(uuid string) error
    AddSubtask(parentUUID string, raw string) (Task, error)
    Annotate(uuid string, text string) error
    SetScheduled(uuid string, t *time.Time) error
    Start(uuid string) error
    Stop(uuid string) error
}

type TimeTracker interface {
    Start(tags ...string) error
    Stop() error
    Active() (*TimeEntry, error)
    Entries(from, to time.Time) ([]TimeEntry, error)
    Add(e TimeEntry) error
}

type Habits interface {
    Status(day time.Time) ([]Habit, error)
    Log(name string, day time.Time, result HabitResult) error
}

type Notes interface {
    List() ([]NoteRef, error)
    Read(path string) (string, error)
    CreateFromTemplate(kind, title string, vars map[string]string) (string, error)
    AppendLine(path, line string) error
    UpdateAutoSection(path, content string) error
}

type Editor interface { Command(path string) *exec.Cmd }  // rulat prin tea.ExecProcess
type Notifier interface { Send(title, body string) error }
```

Tipurile de domeniu (`Event`, `Task`, `TimeEntry`, `Habit`) sunt definite în `core` și nu conțin câmpuri specifice uneltelor. Traducerea (de ex. `+obiectiv` → `Kind = Objective`, UDA `durata` → `Target`) se face exclusiv în adaptoare.

### 9.4 Reguli pentru adaptoare

- Citirea se face prin **comenzile de export** ale uneltelor, nu prin fișierele lor interne:
  - Taskwarrior: `task rc.verbose=nothing rc.confirmation=off … export`
  - Timewarrior: `timew export <interval>`
  - harsh: `harsh log --json`
  - khal: `khal list` cu ieșire structurată. Se verifică în versiunea instalată dacă există `--json`; altfel `--format` cu un separator de câmpuri care nu apare în text (de ex. `\x1f`), cu atenție la descrierile pe mai multe rânduri.
- Excepție: scrierea în log-ul harsh se face prin adăugarea unei linii `AAAA-LL-ZZ : Nume : y` în fișierul de log.
- Duratele din Taskwarrior vin în format ISO 8601 (`PT3H`) și se parsează ca atare.
- Erorile uneltelor (comandă lipsă, ieșire neașteptată) se afișează în bara de stare. Aplicația nu se oprește din cauza unui singur adaptor defect: ecranul afectat afișează eroarea, celelalte funcționează.

### 9.5 Linia de comandă

| Comandă | Efect |
|---|---|
| `dashboard` | pornește TUI-ul pe ecranul implicit |
| `dashboard --page agenda\|sarcini\|timp\|notite` | pornește pe ecranul dat |
| `dashboard notify` | verifică evenimentele și blocurile care încep în următoarele N minute și trimite notificări; destinat unui timer systemd |
| `dashboard import-timp` | rulează importul din 5.6 |
| `dashboard jurnal` | generează/actualizează jurnalul zilei și îl deschide în editor |

`dashboard notify` ține evidența notificărilor deja trimise într-un fișier de stare în `$XDG_STATE_HOME`, ca să nu le repete.

### 9.6 Reîmprospătarea datelor

- Datele se reîncarcă la pornire, la schimbarea ecranului, după orice acțiune de scriere și periodic (interval configurabil, implicit 60 s).
- Cronometrul activ din bara de sus se actualizează la fiecare secundă fără a reîncărca datele.

---

## 10. Configurare

`~/.config/dashboard/config.toml`: vezi [`config.example.toml`](../config.example.toml) din rădăcina depozitului (identic cu exemplul din specificația originală).

---

## 11. Ce NU face aplicația

- Nu gestionează finanțe.
- Nu editează notițe în interfață.
- Nu are bază de date proprie și nu duplică date din unelte.
- Nu sincronizează nimic (vdirsyncer, git și Syncthing se ocupă de asta).
- Nu scrie în calendarele Google.
- Nu pornește cronometrul automat.
- Nu are versiune mobilă și nu este multi-utilizator.
- Nu are layout configurabil în prima versiune.
- Nu afișează grafice pentru jurnalele de progres în prima versiune.

---

## 12. Testare

- **Nucleu:** teste unitare cu adaptoarele `fake` și ceas fix, pentru toate regulile din secțiunea 5 (inclusiv cazurile limită: interval activ, suprapuneri parțiale, peste 100%, schimbare de săptămână/lună).
- **Teste de contract** pentru fiecare interfață, rulate atât pe adaptorul `fake`, cât și pe cel real. Orice adaptor nou trebuie să le treacă.
- **Integrare cu uneltele reale** în directoare temporare, folosind variabilele de mediu `TASKRC`, `TASKDATA`, `TIMEWARRIORDB`, `HARSHPATH` și o configurare khal temporară. Aceste teste se sar automat dacă unealta nu e instalată.
- Nicio funcție nu se consideră terminată fără teste.

---

## 13. Etape de implementare

Fiecare etapă se încheie cu o aplicație funcțională și testată. Nu se începe etapa următoare înainte de confirmarea autorului.

1. **Fundația:** structura proiectului, configurarea, interfețele, adaptoarele `fake`, schelet UI cu taburi, bară de sus și jos, meniul `Space`, ajutorul `?`.
2. **Sarcini și timp:** adaptoarele Taskwarrior și Timewarrior; ecranul Sarcini (secțiuni, subtask-uri, adăugare, bifare, modificare, ștergere); cronometrul și bara de sus.
3. **Agenda:** adaptorul khal; ecranul Agendă; sarcinile cursurilor; blocurile cu progres; împrumutul de subtask-uri; crearea de blocuri.
4. **Timp:** ecranul Timp; plan vs. realitate; adăugare manuală; importul de pe telefon.
5. **Notițe:** adaptorul de notițe și editorul; ecranul Notițe; șabloane; jurnalul zilnic cu secțiunea automată; captura în inbox.
6. **Obiceiuri și rutina:** adaptorul harsh; secțiunea Rutine; obiceiurile automate; fluxul de sfârșit de perioadă pentru obiective; revizuirea săptămânală; `dashboard notify`.

---

## 14. Instrucțiuni pentru asistentul AI

- Lucrează strict pe etapa curentă. Nu adăuga funcții care nu sunt în această specificație.
- Când specificația este ambiguă sau intră în conflict cu comportamentul real al unei unelte, **întreabă** înainte de a decide.
- Verifică formatul exact al ieșirii fiecărei unelte în versiunea instalată, nu din memorie.
- Folosește întotdeauna UUID-uri pentru sarcini.
- Nicio logică de domeniu în adaptoare și niciun apel direct la unelte din nucleu sau UI.
- Scrie testele odată cu codul.
- La finalul fiecărei sesiuni, rezumă ce s-a făcut, ce a rămas și orice abatere de la specificație.
