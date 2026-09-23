# Revue d’architecture — Purple Replay 1.0.6

Revue du 18 septembre 2026, avec corrections et tests exécutés localement.

## Organisation

| Couche | Responsabilité | Dépendances autorisées |
| --- | --- | --- |
| `backend/app/domain` | Calculs, compte simulé, horloge et contrats de source | Bibliothèque standard et utilitaires métier de `core` |
| `backend/app/repositories` | SQLite, JSON et JSONL | Domaine et adaptateurs bas niveau |
| `backend/app/services` | Orchestration du replay, du marché et du journal | Domaine, contrats ciblés et adaptateurs de stockage |
| `backend/app/bootstrap.py` | Assemblage explicite d’un conteneur par espace | Implémentations concrètes ; aucun transport FastAPI |
| `backend/app/api` | Validation et transport HTTP/WebSocket | Schémas et conteneur fourni à la requête |
| `frontend/lib/domain` | Calculs, types, sizing, profils et études | Aucun store Svelte, transport ou composant |
| `frontend/lib/application` | État Svelte et orchestration des interactions | Domaine et adaptateurs API/WebSocket |
| `frontend/lib/api`, `websocket` | Transport navigateur | Types du domaine |
| `frontend/lib/components` | Affichage et interactions graphiques | Couche application et calculs |

Les calculs sont séparés de la persistance et du transport. Les contrôleurs de graphique restent responsables du rendu ; les stores gèrent la session et les requêtes. Le dossier `frontend/` à la racine contient le point d’entrée Vite et son build ; les composants du module sont dans `replay/frontend/`.

## Principes SOLID appliqués

- **Responsabilité unique :** l’API n’assemble plus les services ; `bootstrap.py` s’en charge. Le catalogue local centralise les séances récentes. Les stores ont quitté le dossier de calculs métier.
- **Ouverture et substitution :** les deux générations d’archives utilisent la même façade de lecture. Un test vérifie le changement d’archive puis le retour à la première, sans conserver les mauvaises bougies en cache.
- **Interfaces ciblées :** `services/ports.py` définit les besoins du catalogue, de la projection gamma, de l’historique et du curseur. Le moteur reçoit un `PriceListener` et un chargeur de bougie ; l’outil VP reçoit une interface de dessin minimale.
- **Injection et encapsulation :** les collaborateurs sont fournis lors de l’assemblage. Le câblage circulaire moteur/marché/ordres passe par une méthode publique, utilisable seulement avant chargement. Aucun module applicatif Python n’accède aux attributs privés d’un autre objet.

SOLID est un ensemble de principes, pas une certification. Certains services historiques gardent des annotations de repositories concrets et les stores utilisent les adaptateurs HTTP partagés. Cette revue ne prétend donc pas à une architecture hexagonale intégrale ni à une preuve formelle de substituabilité. Ces limites sont explicites ; aucune abstraction générale supplémentaire n’a été ajoutée sans besoin.

## Dépendances et déploiement

- `requirements.in` : dépendances Python directes, avec versions.
- `requirements.txt` : graphe runtime figé, 17 distributions.
- `requirements-dev.in` et `requirements-dev.txt` : outils de test et de contrôle séparés. HTTPX appartient uniquement aux tests.
- `frontend/package-lock.json` : graphe npm figé, réinstallable avec `npm ci`. SvelteKit et son adaptateur inutilisés sont retirés.
- Le conteneur contient Python, ses dépendances runtime, le backend et les fichiers web compilés. Il ne contient ni Node, ni pytest, ni Ruff, ni le client HTTP live supprimé.
- Les archives restent dans `/market`, en lecture seule. Les journaux restent dans le volume `/state`. Aucun changement de données de marché n’a été nécessaire pour cette revue.

## Vérifications reproductibles

Depuis la racine, après installation des dépendances de développement :

```sh
.venv/bin/python -m pytest -q replay/backend/tests
.venv/bin/ruff check replay/backend/app replay/backend/tests
.venv/bin/ruff format --check replay/backend/app replay/backend/tests
npm ci --prefix frontend
npm run check --prefix frontend
node --test replay/frontend/tests/domain.test.cjs
npm run build --prefix frontend
```

53 tests Python et 12 tests front couvrent notamment le moteur, les ordres, l’isolation des espaces, le changement d’archive et les frontières entre couches. Le graphe Python interne est contrôlé sans cycle. Ruff vérifie les imports, erreurs statiques ciblées et le formatage. Ce contrôle ne remplace pas un typage statique complet du backend.

Deux avertissements de dépréciation proviennent du client de test Starlette/HTTPX et d’AnyIO ; ils ne sont pas masqués. Aucun changement de version de ces bibliothèques n’a été mélangé à cette revue.

## Correctif 1.0.2 — compte et gamma

Le composant compte utilise un calcul de valorisation pur et testé : pas de total inventé lorsque le prix manque, pas de double déduction des frais. `application/GammaStore.ts` fournit une source partagée à la carte et aux lignes gamma. Il suit le symbole et le curseur de la séance chargée, invalide les réponses tardives, efface les niveaux au retour en arrière et retente les erreurs. Les instruments sans gamma sont identifiés explicitement.

Le cas ES → NQ à la même heure du 18 septembre a été reproduit sur la 1.0.1 (carte vide malgré une réponse API non vide). Quatre tests front supplémentaires couvrent ce correctif : 12 tests front au total.


## Profils historiques — 1.0.4

Le calcul pur `domain/replay/volume_profile.py` regroupe les volumes enregistrés en 32 tranches de prix, conserve leur somme et calcule un POC de tranche ainsi qu’une zone de valeur contiguë couvrant au moins 70 % du volume. `RegimesService` alimente le calcul par journée UTC et par bloc horaire ; les profils sont précalculés dans `regimes.json`. Le composant de présentation `VolumeProfile.svelte` affiche les mêmes données sur mobile et grand écran. Les profils du catalogue sont rétrospectifs (période complète), sans inventer les volumes manquants.


## Audit de maintenance — 1.0.5

Le build Docker assemblait auparavant seulement le runtime Python et copiait `frontend/dist` : une modification Svelte non compilée pouvait donc manquer dans l’image. Il construit désormais le front dans une étape Node distincte avec le lockfile, Svelte-check et génération automatique de la documentation. Le runtime conserve seulement Python et les fichiers web résultants. Le contexte Docker utilise une liste explicite : aucune archive, journal, configuration locale ou environnement de développement n’est envoyé au build.

La version publique est suivie dans Git. Les archives de marché sont distribuées
séparément dans le paquet de release. Les espaces par cookie séparent les exercices
locaux ; ils ne constituent pas une authentification multiutilisateur forte.
Les images de base utilisent des tags : reproductibilité bit à bit non garantie.
US500 n’est pas inclus dans cet instantané.

Les schémas de chargement, vitesse et stop à zéro refusent maintenant les valeurs non finies. Trois cas paramétrés vérifient Infinity, -Infinity et NaN avant appel au domaine. Les contrôles ont passé 53 tests Python et 12 tests front ; deux dépréciations de bibliothèques de test restent visibles.


## Vérification navigateur et développement — 1.0.6

Le proxy Vite conserve désormais Host (`changeOrigin: false`) pour les requêtes API et WebSocket : les POST du mode développement ne sont plus rejetés par le contrôle same-origin. La protection du backend reste active. Le graphique indique explicitement le chargement de son historique ; les captures doivent attendre la réponse des bougies avant d’évaluer leur rendu. Le rendu des bougies, études, volumes et gamma a été vérifié après chargement.

## Distribution publique 1.1.0

Le journal et le graphique ne lisent plus les anciens trades réels. La route de ces
trades, leurs marqueurs et leurs lecteurs ont été retirés. Même une archive contenant
des transactions personnelles fictives en test ne les ajoute pas au journal simulé.
Les archives publiques sont créées dans des fichiers neufs : tables de marché
autorisées seulement, identifiants de ticks régénérés, aucune table de compte.
Le réseau Docker est interne, le port est local et le navigateur utilise une CSP
limitée aux ressources de l’instance. Les données de marché sont en lecture seule.

Le lockfile impose `@types/estree` 1.0.9 : les dépendances demandaient une version
1.1.0 absente du registre lors du contrôle. Svelte-check et le build valident cette
configuration. Aucun client HTTP externe n’est installé dans le runtime.
