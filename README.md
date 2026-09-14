# PurpleChart · Interactive showcase

Une vitrine interactive de **PurpleChart V2**, conçue par **Mr-yums** et développée avec assistance IA. Ce module public propose une expérience simplifiée : graphique en chandeliers, navigation dans une session fictive et journal de démonstration.

![Interface de démonstration, données synthétiques](docs/showcase.png)

## Essayer

Avec Docker et Docker Compose :

```sh
git clone https://github.com/Mr-yums/PurpleChart-showcase.git
cd PurpleChart-showcase
docker compose up -d --build
```

Ouvrir **http://127.0.0.1:8948/**. Arrêt : `docker compose down`. Relance : `docker compose up -d`. Aucun compte, abonnement ni clé API requis. Le port est lié à la machine locale ; ce dépôt ne fournit pas d’hébergement Internet permanent.

## Image prête à lancer

Une image **Linux amd64 (x86-64)** est disponible dans la [release 0.1.0](https://github.com/Mr-yums/PurpleChart-showcase/releases/tag/v0.1.0), avec `compose.download.yaml` et `SHA256SUMS`. Après téléchargement des trois fichiers dans le même dossier :

```sh
sha256sum -c SHA256SUMS
docker load -i purplechart-showcase-0.1.0-linux-amd64.tar.gz
docker compose -f compose.download.yaml up -d
```

Même adresse : http://127.0.0.1:8948/. Arrêt : `docker compose -f compose.download.yaml down`. Relance : `docker compose -f compose.download.yaml up -d`. Sur ARM, construire depuis les sources plutôt qu’utiliser cette archive amd64. Ne pas lancer les deux variantes simultanément sur le même port.

## Trois modules publics

- **Marché** : deux instruments fictifs NQ/ES, chandeliers, volumes et moyenne mobile simple à 12 périodes. Tous les prix sont générés mathématiquement dans le navigateur.
- **Replay de démonstration** : pause, reprise, vitesse et curseur de navigation dans 240 bougies synthétiques. Ce n’est pas le moteur Replay privé.
- **Journal** : transactions inventées, filtre par instrument et brouillon éphémère. Aucune persistance ; recharger efface le brouillon.

## Architecture et périmètre

Le projet privé associe Svelte, Python et Go. Cette vitrine est une **implémentation distincte**, en Go + HTML/CSS/JavaScript, sans dépendance JavaScript, CDN, police distante ou accès réseau depuis l’interface. Elle illustre une expérience et des choix de conception ; elle n’expose pas le code complet de PurpleChart.

```text
Navigateur → serveur Go → interface embarquée
     └──── données synthétiques générées localement
```

Le moteur de trading, les stratégies, les réglages privés, les adaptateurs broker et les automatisations restent privés. Les clés, comptes, soldes, historiques réels, bases et configurations d’infrastructure sont absents du dépôt et de l’image.

Docker facilite la distribution, **il ne rend pas son contenu secret**. L’image ne contient que le binaire de la vitrine et les trois fichiers web embarqués. Elle tourne sans privilèges, avec un système de fichiers en lecture seule, sans volume ni secret injecté. Le port publié reste limité à la boucle locale. Le réseau Docker standard n’interdit pas, à lui seul, les sorties réseau du conteneur ; le serveur fourni n’en effectue aucune. La politique du navigateur interdit les connexions réseau initiées par la page (`connect-src 'none'`).

## Vérifier et faire évoluer

`go test ./...` contrôle la surface HTTP autorisée, le refus des routes de trading et les en-têtes de confinement. Le workflow GitHub teste également la construction Docker, le démarrage et le refus d’une route d’ordres. Aucun test n’appelle un broker.

Les prochains modules doivent rester autonomes et utiliser des données fictives. Ne pas copier le dépôt privé dans le contexte Docker. Le fichier `.dockerignore` autorise seulement les entrées nécessaires à la construction.

Cette vitrine ne démontre aucune performance financière ni rentabilité. Les fonctions de production et la sécurité du projet privé ne sont pas certifiées par cette démonstration.

## English

Interactive portfolio showcase by **Mr-yums**, built with AI assistance. A standalone Go server embeds a dependency-free web interface with synthetic candlesticks, a playback timeline and a fictional trading journal. No broker integration, private strategy, credentials or real trading data are included. Run `docker compose up -d --build`, then open http://127.0.0.1:8948/.

Implementation assistance: [Sol].
