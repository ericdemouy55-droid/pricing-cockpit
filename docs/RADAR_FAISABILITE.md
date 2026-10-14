# Eurotyre Market Price Radar — faisabilité des sources

Audit du 14 octobre 2026. Ce rapport distingue consultation publique, permission d’extraction et disponibilité d’un flux. Un robots.txt accessible ne constitue pas une licence de réutilisation. Aucune autorisation partenaire, licence de prix ni API contractuelle n’a été fournie dans cette session.

| Enseigne | Vérification effectuée | Restrictions observées | Accès automatisé retenu | État réel |
| --- | --- | --- | --- | --- |
| Norauto | CGU officielles consultées ; requête directe à robots.txt | Les CGU limitent les droits d’utilisation et imposent une autorisation pour certaines extractions/réutilisations. robots.txt a répondu HTTP 403 au collecteur d’audit. | Flux autorisé ou fichier dont la provenance et les droits sont confirmés | Extraction du site désactivée ; aucun flux réel testé |
| Euromaster | Mentions légales officielles et robots.txt consultés | Les droits annoncés visent l’usage personnel non commercial. robots.txt exclut notamment des interfaces de recherche de prix et des endpoints Ajax. | Flux partenaire autorisé ou import CSV/Excel autorisé | Extraction du site désactivée ; aucun flux réel testé |
| Feu Vert | Mentions légales/CGU et robots.txt consultés | Réutilisation encadrée par les droits de propriété intellectuelle ; robots.txt exclut notamment /api/, /recherche/, /product* et certains paramètres de centre | Flux partenaire autorisé ou import CSV/Excel autorisé | Extraction du site désactivée ; aucun flux réel testé |
| First Stop | Conditions générales officielles et robots.txt consultés | Les conditions réservent les droits sur les contenus et demandent une autorisation écrite pour leur usage, sauf permission légale. robots.txt n’autorise pas à lui seul une veille commerciale ; les offres peuvent dépendre du site du centre. | Flux partenaire autorisé ou import CSV/Excel autorisé | Extraction du site désactivée ; aucun flux réel testé |

La décision du pilote est de développer quatre adaptateurs indépendants vers des sources autorisées. Les essais de ces adaptateurs utilisent des fichiers fictifs ou des réponses simulées. Ils ne prouvent pas qu’un accès commercial aux quatre enseignes existe. Aucune API publique de catalogue/prix utilisable pour ce pilote n’a été identifiée dans les pages officielles examinées ; cela ne prouve pas l’absence de flux partenaires.

## Sources primaires

- [Norauto — CGU](https://www.norauto.fr/e/conditions-generales-utilisation.html)
- [Norauto — robots.txt](https://www.norauto.fr/robots.txt) — HTTP 403 lors du contrôle direct.
- [Euromaster — mentions légales](https://www.euromaster.fr/mentions-legales)
- [Euromaster — robots.txt](https://www.euromaster.fr/robots.txt) — HTTP 200 lors du contrôle direct.
- [Feu Vert — mentions légales et CGU](https://www.feuvert.fr/static/mentions_legales-3294.html)
- [Feu Vert — robots.txt](https://www.feuvert.fr/robots.txt)
- [First Stop — conditions générales](https://www.firststop.fr/conditions-generales)
- [First Stop — robots.txt](https://www.firststop.fr/robots.txt) — HTTP 200 lors du contrôle direct.

## Conditions de mise en service

Pour chaque source : conserver la référence de l’autorisation, son responsable, sa durée, le domaine autorisé et le format du flux. Vérifier sur quelques EAN réels les identités, le centre, la TVA, la nature du prix et les promotions. Une réponse 401/403/429, une redirection ou une erreur met le connecteur en échec sans tentative de contournement. Un échec d’une enseigne n’arrête pas les autres.

Compiègne est une zone proposée, pas un centre implicitement choisi ni une preuve de couverture des quatre enseignes. Les identifiants des centres ou le caractère national du flux doivent être précisés dans les données et dans les paramètres. L’audit doit être actualisé lorsque les conditions ou les sources changent.
