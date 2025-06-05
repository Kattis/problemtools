**EKO! Eko! Ek...**

![CC-BY-SA 2.0 By William Craig on wikimedia.org](cave.jpg)

Du älskar att skrika i grottor för att höra dina ord ekade tillbaka till dig. Tyvärr, som en hårt arbetande mjukvaruingenjör, har du
inte tid för att komma ut och skrika i grottor så ofta. Istället skulle du vilja implementera ett program som fungerar som en ersättning för en grotta.

Ibland vill du mata in några ord i programmet och få dem ekade tillbaka till dig. Men, som det är välkänt, om du skriker för snabbt i en grotta kan ekot störa de nya ord du säger. [^1] Mer specifikt, vartannat ord du säger kommer att störa ekot av ditt tidigare ord. Därför kommer endast det första, tredje, femte och så vidare ordet faktiskt att producera ett eko.

Din uppgift är att skriva ett program som simulerar detta beteende.

## Indata

Den första raden av indata innehåller ett heltal $N$ ($1 \le N \le 10$).

De följande $N$ raderna innehåller vardera ett ord. Varje ord är högst $100$ bokstäver långt och innehåller endast bokstäverna `a-z`.

## Utdata

Skriv ut de ord som har udda index (dvs. första, tredje, femte och så vidare) i inmatningen.


## Poängsättning

Din lösning kommer att testas på en mängd testfallsgrupper.
För att få poäng för en grupp så måste du klara alla testfall i gruppen.

| Grupp | Poäng | Begränsningar            |
|-------|-------|--------------------------|
| 1     | 1     | $N$ är alltid $5$        |
| 2     | 1     | Inga ytterligare begränsningar |

[^1]: [https://sv.wikipedia.org/wiki/Interferens](https://sv.wikipedia.org/wiki/Interferens)
