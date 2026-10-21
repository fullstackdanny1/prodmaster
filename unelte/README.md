# Unelte

Comenzi de terminal și servicii locale care înlocuiesc unelte online plătite: backup automat cu Git,
organizarea descărcărilor, OCR din captură de ecran, Markdown → Word/PDF cu șablonul facultății,
verificarea formatării, corectură (LanguageTool local), traducere și rezumatul zilnic din RSS.
Plus Stirling-PDF, Excalidraw și ChartDB, rulate local.

Sisteme: **Ubuntu/Debian**, **Fedora** și **Arch**, cu orice mediu grafic. Specificația completă:
[`SPECIFICATIE.md`](SPECIFICATIE.md).

| Comandă | Rol |
|---|---|
| `backup` | commit și push automat pentru folderele importante (+ copii ale bazei Zotero) |
| `organizeaza` | mută fișierele descărcate după reguli; implicit doar arată planul |
| `ocr-ecran` | text dintr-o zonă a ecranului, direct în clipboard |
| `converteste` | Markdown → Word (și PDF) cu profilul facultății |
| `verifica-format` | verifică un `.docx` (sau citările unui `.md`) după profil |
| `corecteaza` | gramatică și ortografie cu LanguageTool local; stil prin AI la cerere |
| `traduce` | traducere prin AI cu păstrarea formatării |
| `rezumat` | rezumatul zilnic din sursele RSS/Atom, ca notiță |
| `unelte doctor` | starea instalării și a fiecărei comenzi |
| `unelte ai …` | test, modele, sarcini și consum pentru stratul AI |

Fiecare comandă are `--help` în română, cu exemple. Coduri de ieșire: 0 = succes,
1 = probleme găsite (de exemplu erori de formatare), 2 = eroare de utilizare sau de mediu.

## Instalare

```bash
git clone … ~/unelte && cd ~/unelte
./install.sh
```

`install.sh` e idempotent (îl poți rula oricând, de exemplu după `git pull`) și nu suprascrie
niciodată configurația. Pași:

1. detectează distribuția (sau `--distro debian|fedora|arch`) și verifică Python ≥ 3.11 și `venv`;
2. creează `.venv` și instalează `python-docx` (doar dacă `requirements.txt` s-a schimbat);
3. creează `~/.config/unelte/` (`config.toml`, `dictionar.txt`, `glosar.toml`) și `~/.config/ai/`
   (`ai.toml`, `.env` cu permisiuni `600`), dacă lipsesc;
4. scrie lansatoarele în `~/.local/bin/` (te avertizează dacă folderul nu e în `PATH`);
5. instalează și activează timer-ele systemd de utilizator (`--fara-systemd` sare pasul);
6. afișează **o singură** comandă de instalare pentru programele de sistem lipsă și o rulează doar
   după confirmare (sau cu `--da`); niciodată `sudo` fără să-ți arate comanda;
7. descarcă LanguageTool (`--fara-languagetool` sare pasul);
8. rulează `unelte doctor`.

Alte opțiuni: `--servicii` (pornește Stirling-PDF, Excalidraw și ChartDB),
`--dezinstaleaza` (elimină timer-ele și lansatoarele; configurația și datele rămân).

Pe **Ubuntu/Debian** modulul `venv` vine separat: `sudo apt install python3-venv`.

Programele de sistem (lista completă, pe distribuții, e în [`distro.toml`](distro.toml)):

| Pentru | Ubuntu / Debian | Fedora | Arch |
|---|---|---|---|
| `converteste` | `pandoc libreoffice-writer libreoffice-math` | `pandoc libreoffice-writer libreoffice-math` | `pandoc libreoffice-fresh` |
| `ocr-ecran` | `tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng` | `tesseract tesseract-langpack-ron tesseract-langpack-eng` | `tesseract tesseract-data-ron tesseract-data-eng` |
| captură Wayland (sway, Hyprland) | `grim slurp wl-clipboard` | idem | idem |
| captură X11 | `maim xclip` | idem | idem |
| `corecteaza` (Java) | `default-jre-headless` | `java-21-openjdk-headless` | `jre-openjdk-headless` |
| `backup` | `git` | `git` | `git` |
| notificări | `libnotify-bin` | `libnotify` | `libnotify` |

`libreoffice-math` e necesar pentru formulele din PDF: fără el, LibreOffice omite ecuațiile la export.

Lipsa unui program dezactivează doar comanda care are nevoie de el, cu un mesaj care conține
comanda de instalare pentru distribuția ta.

## Configurare

Toată configurația stă în `~/.config/unelte/config.toml` (pornește de la
[`config.example.toml`](config.example.toml)); un fișier gol funcționează.

### AI (comun cu Studiu)

Furnizorii, modelele și ce model folosește fiecare sarcină stau în `~/.config/ai/ai.toml`;
cheile în `~/.config/ai/.env`. Sarcinile Unelte: `corectura_ocr`, `stil`, `traducere`, `rezumat`.
Orice comandă cu AI acceptă `--model <alias sau furnizor:model>`, cu prioritate față de `ai.toml`.

- **Gemini (implicit, gratuit):** cheie din Google AI Studio → `GEMINI_API_KEY=...` în `~/.config/ai/.env`.
- **Ollama (local):** `implicit = "ollama:qwen3:8b"` în `ai.toml`; pe un laptop fără placă video
  modelele locale sunt lente și greșesc mai des în română; potrivite pentru sarcinile `rapid`.
- **Furnizor plătit:** decomentează secțiunea lui în `ai.toml`, pune cheia în `.env`, setează
  prețurile și eventual `[buget].lunar_usd`.

```bash
unelte ai test                 # un apel minim către modelul implicit
unelte ai modele gemini        # modelele disponibile la furnizor
unelte ai sarcini              # sarcină → model rezolvat
unelte ai consum               # consumul lunii (Studiu + Unelte)
```

Fără cheie, comenzile care au nevoie de AI spun exact ce lipsește; restul merge normal
(`ocr-ecran` fără `--ai`, `corecteaza` fără `--stil`, `rezumat` cu titluri și linkuri).

## Comenzile

### `backup`

```toml
[backup]
interval = "1h"
fisier_max_mb = 50

[[backup.repo]]
nume = "notite"
cale = "~/Notite"
```

```bash
backup --initializeaza notite   # git init, .gitignore, primul commit
git -C ~/Notite remote add origin git@github.com:<utilizator>/notite.git
backup                          # toate repo-urile; backup --doar notite
backup --stare                  # ultimul backup reușit, per repo și remote
```

Pentru fiecare repo: verificări de siguranță (fișiere peste limită, fișiere care par secrete –
`.env`, `*.pem`, `id_rsa*`, chei private, `API_KEY=…` – sau un merge/rebase în curs blochează repo-ul),
commit `backup automat AAAA-LL-ZZ HH:MM`, apoi `pull --rebase --autostash` și `push` spre **fiecare**
remote. La conflict: `rebase --abort`, notificare urgentă, commit-ul rămâne local. **Niciodată push forțat.**
Serverul privat se adaugă mai târziu cu `git remote add privat …`. Timer-ul rulează la `interval`,
cu `Persistent=true` (o rulare ratată cât laptopul a stat închis se face la pornire). Succesul e tăcut;
notificare doar la erori.

Zotero (`[backup.zotero]`): dacă Zotero nu rulează, copiază `zotero.sqlite` (și `better-bibtex.sqlite`)
în `destinatie/AAAA-LL-ZZ_HHMM/` și păstrează ultimele `copii_pastrate`.

### `organizeaza`

```bash
organizeaza              # planul: fișier → destinație [regula], fără nicio mutare
organizeaza --aplica     # execută exact planul afișat
organizeaza --anuleaza   # readuce fișierele din ultima rulare
organizeaza --istoric
```

Prima regulă care se potrivește câștigă; cuvintele se potrivesc fără majuscule și fără diacritice.
În `destinatie` merg `{an}`, `{luna}`, `{zi}` (data modificării) și `{extensie}`. Mutările nu
suprascriu niciodată (`nume (2).pdf`). Timer-ul orar aplică doar regulile cu `automat = true`.
`cuvinte_continut` (textul primei pagini a PDF-ului) folosește `pdftotext` (pachetul `poppler-utils`).

### `ocr-ecran`

Selectezi o zonă, textul ajunge în clipboard. Unealta de captură se alege după mediu:
sway/Hyprland → `slurp` + `grim`; GNOME → `gnome-screenshot`; KDE → `spectacle`; X11 → `maim`
(sau forțat din `[ocr].captura`). Esc anulează fără eroare.

```bash
ocr-ecran                      # + notificare cu primele cuvinte
ocr-ecran --ai                 # corectează erorile tipice de OCR prin AI
ocr-ecran --fisier slide.png   # OCR pe o imagine, textul la ieșirea standard
ocr-ecran --salveaza           # păstrează captura în ~/Imagini/ocr/
```

Comenzile se rulează din terminal; dacă vrei o scurtătură în mediul tău grafic, leag-o de `ocr-ecran`.

### `converteste` și `verifica-format`

```bash
converteste lucrare.md               # → lucrare.docx (+ verificarea formatării la final)
converteste lucrare.md --pdf         # → și lucrare.pdf, prin LibreOffice
converteste lucrare.md --profil licenta
converteste notita.md --fara-pagina-titlu
verifica-format lucrare.docx [--raport raport.md]
verifica-format lucrare.md           # citările față de bibliografie
```

Antetul YAML completează pagina de titlu:

```yaml
---
universitate: Universitatea din București
facultate: Facultatea de Administrație și Afaceri
titlu: Analiza lichidității
autor: Ana Pop
coordonator: Prof. dr. Ion Ionescu
oras: București
an: 2026
cuprins: true
---
```

Citările se scriu `[@cheie]` sau `[@cheie, p. 12]`, iar bibliografia e exportul automat Better BibTeX
(`[documente].bibliografie`); cheile inexistente sunt semnalate înainte de conversie. Formulele LaTeX
devin ecuații Word native, iar imaginile se caută relativ la fișier. PDF-ul se face din `.docx` cu
LibreOffice (fără LaTeX), într-un profil temporar, deci merge și cu LibreOffice deschis; cuprinsul e
completat automat în PDF, iar în `.docx` apare după clic dreapta → „Actualizare câmp” în Word.
Dacă documentul e deschis în Word/LibreOffice, rezultatul se scrie alături (`lucrare (2).docx`).

`verifica-format` calculează **formatarea efectivă** a fiecărui paragraf (run → paragraf → lanțul de
stiluri `based_on` → `docDefaults`) și verifică pagina (format, margini cu toleranță 0,05 cm, număr
de pagină), textul (font, mărime, spațiere, aliniere, indent), titlurile (font, mărime, ierarhie),
legendele figurilor și bibliografia (sau câmpurile Zotero). Problemele repetate se comprimă:
„140 de paragrafe au Arial 11 în loc de Times New Roman 12 (primul: §12 «…»)”.

**Profiluri.** Un profil e un folder cu `profil.toml`, `reference.docx`, `stil.csl` și
`pagina-titlu.lua`, căutat în `~/.config/unelte/profiluri/<nume>/`, apoi în `profiluri/<nume>/`.
Ca să-ți faci profilul (de exemplu `licenta`): copiază `profiluri/facultate` în
`~/.config/unelte/profiluri/licenta`, completează `profil.toml` după ghidul facultății și regenerează
șablonul Word:

```bash
.venv/bin/python profiluri/genereaza_reference.py ~/.config/unelte/profiluri/licenta
```

`unelte doctor` verifică dacă `reference.docx` corespunde cu `profil.toml`. Stilul de citare implicit
e APA ediția a 7-a (din [citation-style-language/styles](https://github.com/citation-style-language/styles),
CC BY-SA 3.0); poți pune orice alt fișier `.csl`.

### `corecteaza`

LanguageTool rulează local, ca serviciu de utilizator (`unelte-languagetool`), doar pe
`127.0.0.1:8081`. Pentru extensia LanguageTool din browser: setările extensiei → „Experimental” /
„Server LanguageTool local” (sau „Other server”) → `http://127.0.0.1:8081/v2`.

```bash
corecteaza text.md                  # raport: linie:coloană, mesaj, sugestii
corecteaza text.md --interactiv     # 1–9 aplică, s sare, i ignoră regula, a adaugă în dicționar, q termină
corecteaza text.md --stil           # + rescriere de stil prin AI în text.stil.md și diferențele
corecteaza lucrare.docx             # doar raport, pe paragrafe
echo "text" | corecteaza -
corecteaza --adauga-cuvant Studiu
```

În Markdown, antetul, codul, formulele, URL-urile și sintaxa linkurilor sunt mascate cu spații, ca
pozițiile să corespundă textului original. Rezultatele merg în `<nume>.corectat.md`, niciodată
peste original. Dicționarul personal: `~/.config/unelte/dictionar.txt`; regulile ignorate:
`[corecteaza].reguli_ignorate`. Dacă serverul nu răspunde: `systemctl --user start unelte-languagetool`.

**LanguageTool:** versiunea instalată e fixată în [`languagetool.toml`](languagetool.toml). Suma
SHA-256 a arhivei nu a putut fi fixată în repo (site-ul LanguageTool nu era accesibil la implementare):
la prima instalare, `install.sh` afișează suma fișierului descărcat și cere confirmare; copiaz-o în
`languagetool.toml`, ca instalările următoare să fie verificate automat. Actualizarea: schimbi versiunea
și suma, apoi rulezi `./install.sh`.

### `traduce`

```bash
traduce articol.md --in en           # → articol.en.md
traduce rezumat.md --in ro --din en
traduce document.docx --in en        # → document.en.docx
echo "text" | traduce - --in en
```

Blocurile de cod, formulele și antetul YAML nu se trimit; codul și formulele inline sunt protejate
cu marcaje care trebuie să revină neschimbate. Dacă numărul de blocuri primite nu corespunde cu cel
trimis, bucata se retrimite o dată, apoi comanda se oprește **fără fișier parțial**. Glosarul
`~/.config/unelte/glosar.toml` are câte o secțiune per limbă țintă:

```toml
[en]
"active circulante" = "current assets"
```

Limitare `.docx`: se păstrează stilul fiecărui paragraf, dar formatarea din interiorul lui
(cuvinte îngroșate izolate, linkuri) se pierde.

### `rezumat`

```toml
[rezumat]
ora = "07:30"
iesire = "~/Notite/Rezumate"
interese = "audit și securitate crypto, piața muncii pentru juniori IT"
max_pe_subiect = 5

[[rezumat.subiect]]
nume = "Securitate crypto"
surse = ["https://exemplu.org/feed.xml"]
```

```bash
rezumat              # rulează acum (timer-ul zilnic, la `ora`, Persistent=true)
rezumat --fara-ai    # doar titlurile și linkurile
rezumat --surse      # verifică fiecare sursă
```

Notița `AAAA-LL-ZZ.md` are antetul `tip: rezumat`, deci apare în Studiu fără să intre în „De revizuit”.
Cereri condiționate (`ETag`, `Last-Modified`), cel mult o descărcare pe zi per sursă, elementele
văzute reținute 60 de zile (fără duplicate de la o zi la alta).

## Servicii locale

```bash
./install.sh --servicii
```

| Serviciu | Adresă | Pentru ce |
|---|---|---|
| Stirling-PDF | <http://127.0.0.1:8090> | operații PDF (unire, împărțire, OCR, compresie) |
| Excalidraw | <http://127.0.0.1:8091> | schițe **libere**: arhitecturi, idei, hărți mentale |
| ChartDB | <http://127.0.0.1:8092> | **proiectarea** bazelor de date: tabele, chei, relații, SQL |

Diagramele simple care fac parte din materie se scriu ca **Mermaid** direct în notițele Studiu.
Regula: dacă diagrama trebuie să apară în notiță și să se schimbe odată cu ea, e Mermaid; dacă e un
desen liber, e Excalidraw; dacă se termină cu un script SQL, e ChartDB.

Excalidraw și ChartDB salvează desenele **în browser**: exportă periodic ce contează (fișier
`.excalidraw` + SVG lângă notițe; JSON/SQL din ChartDB într-un folder inclus în `backup`).
Funcțiile AI ale ChartDB rămân dezactivate (nu se configurează nicio cheie).

Imaginile au versiuni fixate în [`servicii/compose.yml`](servicii/compose.yml) (Excalidraw, care nu
publică tag-uri de versiune, e fixat prin digest). Actualizare: schimbi tag-ul, apoi
`docker compose -f servicii/compose.yml pull && docker compose -f servicii/compose.yml up -d`.
Cu Podman, `install.sh` activează și `podman-restart.service`, ca serviciile să pornească singure
după o repornire.

## Modulele amânate

`cv` și `buget` (secțiunile 12 și 13 din specificație) nu sunt implementate; vor rămâne dezactivate
implicit (`[module]`) și după implementare.

## Teste

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Fără rețea și fără chei reale: servere AI false (format OpenAI și Anthropic), un LanguageTool fals,
procese externe înlocuite; testele care chiar au nevoie de `git` sau `pandoc` sunt sărite automat
dacă programul lipsește. Pachetul `unelte/ai/` e identic cu `app/ai/` din Studiu.

## Depanare

- `unelte doctor` – starea fiecărei comenzi, a AI-ului, a timer-elor și a serviciilor.
- Jurnalele: `~/.local/state/unelte/<comanda>.log`; starea backup-ului: `backup-stare.json`.
- Timer-ele: `systemctl --user list-timers 'unelte-*'`, `journalctl --user -u unelte-backup`.
- „Modelul X nu mai e disponibil”: `unelte ai modele gemini` și actualizează `ai.toml`.
