# Instrucțiuni pentru agentul de cod

- Documentul de referință al proiectului este `SPECIFICATIE.md`. Citește-l integral înainte de orice modificare.
- Implementează pe etape, în ordinea din secțiunea 12. O etapă e terminată doar când testele ei trec
  și aplicația pornește curat cu `./studiu.sh --fara-browser`.
- Pornește de la codul existent (secțiunea 2) și păstrează-i convențiile: interfața și mesajele în română,
  identificatorii din cod în engleză, rutele API în română.
- Respectă principiile „set and forget” din secțiunea 1.2. Nu adăuga dependențe, servicii sau pași de build
  care nu sunt cerute de specificație; dacă una pare necesară, explică de ce înainte s-o adaugi.
- Folderul de notițe e singura sursă de adevăr. `data/` e doar cache și trebuie să poată fi șters oricând.
- AI-ul e modular (secțiunea 5.1): codul aplicației apelează doar `ai.ruleaza(sarcina, ...)` și nu conține
  nimic specific unui furnizor sau model. Pachetul `app/ai/` trebuie să rămână identic cu `unelte/ai/` din
  proiectul Unelte; dacă îl modifici, notează în mesajul commit-ului și crește `AI_LAYER_VERSION`.
- Testele nu folosesc rețeaua și nici chei reale: folosesc serverele AI false (secțiunile 5.1 și 11).
- Sistemele țintă sunt Ubuntu/Debian, Fedora și Arch (secțiunea 10.1). Nu presupune o anumită distribuție
  sau un anumit mediu grafic; numele pachetelor stau în `distro.toml`.
- Nu modifica și nu șterge notițele din `exemplu/` decât pentru a adăuga exemple noi.
