# PurpleChart Showcase · Purple Replay

Clone autonome de la partie replay de PurpleChart V2 : entraînement sur des transactions futures historiques, avec compte et ordres simulés. Le code du moteur, du graphique, du journal et des outils de replay provient du module original, adapté pour Docker.

## Utiliser

1. Choisir une séance et une heure UTC, puis **Charger**.
2. Choisir la vitesse, puis **Lecture** / **Pause**.
3. Régler contrats, risque et ratio ; choisir **Achat** ou **Vente**, ajuster les lignes SL/TP, puis confirmer.
4. Utiliser **Tout fermer**, la clôture partielle ou **Stop à zéro**. Le dernier exige une position en gain.
5. Consulter **Journal** et **Performance**, et enregistrer une session d’entraînement.

Les bougies, le tape, le delta cumulé, les profils de volume et les niveaux gamma sont bornés au curseur. Le catalogue décrit rétrospectivement des blocs horaires : efficiency ratio ≥ 0,6 pour un mouvement directionnel, ≤ 0,2 pour un range, mixte entre les deux. Cette description simple remplace le classifieur privé et ne prédit rien. Le DOM présente les volumes exécutés, pas un carnet d’ordres historique reconstruit.

EMA20/50, VWAP Globex/RTH et bandes, volume profile de séance et mesure de plage sont conservés. Gamma PW/CW/FL disponible sur NQ/MNQ lorsque l’archive le permet : projection indicative depuis le sous-jacent historique (ratio) ou NDX (base future observée), avec le dernier prix du future connu à la date du snapshot. Le signe gamma n’est pas une garantie de comportement du marché.

Les bulles/classifications orderflow privées, dominances, stratégies et overlays Valentini, ainsi que les niveaux vanna privés, ne font pas partie de cette édition. Aucun trade, journal personnel, annotation ou identifiant de compte de l’auteur n’est fourni.

## Docker

Le paquet inclut les données dans `data/` et les sources. Docker recompile le frontend depuis les sources avec `npm ci`, vérifie Svelte, puis assemble le runtime Python avec dépendances figées. Node et les outils de build restent dans une étape séparée, absente de l’image finale.

```sh
docker compose up -d --build
```

Ouvrir `http://127.0.0.1:8948/`. Pour choisir un autre port : `PURPLE_REPLAY_PORT=8950 docker compose up -d`.

```sh
docker compose stop       # arrêt, journaux conservés
docker compose start      # relance
docker compose logs -f    # journaux techniques
```

Les archives sont montées en lecture seule. Le volume `journals` contient les espaces et journaux d’entraînement ; ne pas supprimer ce volume pour conserver ses exercices. Chaque navigateur reçoit un espace distinct via un cookie. Effacer ce cookie ouvre un nouvel espace. Une fenêtre privée permet de tester un autre compte. Au maximum 16 espaces peuvent être chargés simultanément ; les espaces inactifs sont libérés après 30 minutes tout en conservant leurs fichiers. La fermeture du dernier onglet met la lecture en pause. Un arrêt normal du conteneur sauvegarde le curseur et le compte ; **Reprendre** restaure la séance en pause.

Le port HTTP est lié à `127.0.0.1`. Le moteur est sur un réseau Docker interne, sans route par défaut
vers Internet ; les archives sont locales et montées en lecture seule. Le programme
ne contient aucun connecteur broker, aucune connexion Topstep ni champ de clé API.
Le journal contient exclusivement les exercices créés par son utilisateur.
Une passerelle nginx locale transmet uniquement vers le moteur : pas de proxy
vers une adresse choisie par le visiteur, ni de routage IP entre ses réseaux.
Le navigateur ne charge que les ressources de cette installation (politique CSP).
Les liens vers GitHub sont ouverts uniquement à la demande de l’utilisateur.

## Organisation et validation

- `replay/backend/app/` : API, moteur, simulation, services et lecteurs d’archives.
- `replay/frontend/` : vrai workspace replay et composants.
- `frontend/` : application web autonome et build Vite.
- `data/` : archives de marché nettoyées et inventaire.
- `compose.yaml` : service isolé et volume des journaux.

Développement : `npm ci --prefix frontend`, `npm run check --prefix frontend`, `npm run build --prefix frontend`. Tests Python depuis `replay/backend` après installation de `requirements-dev.txt` : `python -m pytest -q`. Tests front : `node --test replay/frontend/tests/domain.test.cjs`.

Les remplissages sont simulés sur les transactions enregistrées : pas de simulation de file d’attente réelle ni de garantie d’exécution broker. Les périodes absentes de l’enregistrement ne sont pas inventées. Les frais sont des paramètres d’entraînement, pas une grille tarifaire tenue à jour.

## Architecture et maintenance

La revue détaillée se trouve dans `docs/ARCHITECTURE.md` et dans l’application sur `/architecture.html`. Le backend sépare domaine, repositories, services, assemblage et API. Le front distingue calculs purs (`lib/domain`), stores (`lib/application`), transport et composants.

Les fichiers `.in` recensent les dépendances Python directes ; les `.txt` figent les graphes installables. Les outils de test et Ruff restent dans les dépendances de développement. Le runtime Docker ne les installe pas.

Après `docker compose up -d`, `npm run dev --prefix frontend` utilise le backend local sur 8948. La variable `REPLAY_BACKEND_URL` permet de choisir une autre instance.

## Maintenance

`scripts/check` lance les tests et reconstruit l’interface. La documentation web est
générée depuis `docs/ARCHITECTURE.md`. Ne pas supprimer le volume `journals` lors
d’une mise à jour. L’application est prévue pour un ordinateur personnel ; ses espaces
par cookie ne remplacent pas des comptes avec mots de passe sur un serveur public.

## Publication

Ce dépôt **PurpleChart-showcase** contient désormais **Purple Replay** : il remplace
la vitrine 0.1.0 aux cours fictifs par le module d’entraînement sur archives réelles.
Conception et pilotage : **Mr.yums**, développement assisté par IA.

Télécharger [Purple Replay 1.1.0 avec ses données](https://github.com/Mr-yums/PurpleChart-showcase/releases/tag/v1.1.0),
extraire le paquet puis lancer Docker depuis le dossier `purple-replay`.
L’installation télécharge les dépendances ; l’utilisation du replay est ensuite locale.
Les sources Git seules n’incluent pas les grosses bases : utiliser le paquet complet.
Les archives représentent environ 5 Go une fois extraites.

Les sources privées, comptes et journaux de l’auteur ne sont pas inclus.
Le code conserve la licence MIT du dépôt (voir `LICENSE`).
Les droits des dépendances tierces restent ceux de leurs licences respectives.
