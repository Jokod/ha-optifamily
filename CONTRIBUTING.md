# Guide de contribution

Merci de votre intérêt pour ce projet ! Toute contribution est la bienvenue : corrections de bugs, améliorations, documentation, traductions, tests.

---

## Avertissement

> **Cette intégration est un projet open-source non officiel et n'est ni affiliée à, ni soutenue par THEMISTO CONSEIL / optiCrèche. Elle utilise le compte personnel de l'utilisateur pour accéder aux données auxquelles celui-ci a accès via le portail optiFamily.**

En contribuant à ce dépôt, vous acceptez que le projet reste indépendant et non affilié à THEMISTO CONSEIL / optiCrèche.

---

## Avant de commencer

1. Vérifiez les [issues ouvertes](https://github.com/jokod/ha-optifamily/issues) pour éviter les doublons.
2. Pour une fonctionnalité importante, ouvrez d'abord une issue de discussion.
3. Lisez le [README](README.md) (côté utilisateur) et, si besoin, la [référence API](docs/API.md) (contributeurs uniquement, identifiants fictifs).

---

## Signaler un bug

Ouvrez une issue avec :

- **Version** de Home Assistant
- **Version** de l'intégration OptiFamily
- **Description** claire du problème
- **Étapes pour reproduire**
- **Comportement attendu** vs **comportement observé**
- **Logs** pertinents (en masquant toute donnée sensible)

### Ce qu'il ne faut JAMAIS inclure dans une issue

- Mots de passe
- Tokens d'accès ou de rafraîchissement
- IBAN, BIC, RUM
- Adresses, numéros de téléphone, e-mails réels
- Réponses API complètes contenant des données personnelles

Utilisez des valeurs fictives : `EMAIL`, `PASSWORD`, `ACCESS_TOKEN`, `ENFANT_ID`, etc.

---

## Proposer une amélioration

Décrivez :

- Le **besoin** ou le cas d'usage
- La **solution** envisagée
- L'impact sur la **sécurité** et la **confidentialité**
- Si applicable, des **exemples d'automatisations** ou d'entités

---

## Soumettre une pull request

### Processus

1. **Forkez** le dépôt.
2. Créez une **branche** depuis `main` :
   ```bash
   git checkout -b feat/ma-fonctionnalite
   # ou
   git checkout -b fix/mon-correctif
   ```
3. Effectuez vos modifications en respectant les conventions ci-dessous.
4. Testez localement si possible.
5. Committez avec un message clair et descriptif.
6. Ouvrez une **pull request** vers `main` en décrivant :
   - ce qui change,
   - pourquoi,
   - comment tester.

### Conventions de code

- Suivre les conventions Home Assistant pour les intégrations custom (`custom_components/`).
- Python **3.13+** (aligné HA 2025.9+) ; **3.14** préféré (runtime HA 2026.x actuel).
- Typage explicite (`from __future__ import annotations`).
- Nommage en anglais pour le code, français/anglais pour les traductions (`strings.json`, `translations/`).
- Pas de dépendances externes inutiles (l'intégration n'a aucune dépendance pip supplémentaire).
- Garder l'intégration en **lecture seule** sauf décision explicite du mainteneur.

### Structure des fichiers

| Fichier / dossier | Rôle |
|---|---|
| `api.py` | Client HTTP, authentification, appels endpoints |
| `coordinator.py` | Polling, cache, persistance des tokens |
| `config_flow.py` | Configuration utilisateur |
| `sensor.py` | Entités Home Assistant |
| `const.py` | Constantes centralisées |
| `exceptions.py` | Hiérarchie d'exceptions |
| `strings.json` / `translations/` | Internationalisation |
| `blueprints.py` | Copie des blueprints vers `config/blueprints` au setup |
| `blueprints/automation/` | YAML d'automatisation (emballés dans le composant HACS) |
| `dashboards/optifamily.fr.yaml` | Lovelace 4 vues (FR) — Mushroom, card-mod, auto-entities, week-planner-card |
| `dashboards/optifamily.en.yaml` | Same layout (EN) |
| `packages/optifamily_helpers.yaml` | Helpers optionnels (phase, silencieux, résumé) |

### Règles de sécurité (obligatoires)

- **Ne jamais** logger de réponses API complètes.
- **Ne jamais** exposer de données du endpoint `/profil` (IBAN, RUM, coordonnées…) dans des entités ou attributs.
- **Ne jamais** committer de credentials ou de données réelles.
- Préférer des messages de log génériques (`Authentification réussie`) plutôt que des dumps de données.
- En cas de doute, ne pas exposer la donnée dans Home Assistant.

### Traductions

- Toute nouvelle clé UI doit être ajoutée dans `strings.json`.
- Fournir au minimum les traductions **français** (`translations/fr.json`) et **anglais** (`translations/en.json`).

### Tests & lint

- Ajoutez des tests pour toute nouvelle logique métier significative.
- Utilisez des fixtures avec des données fictives.
- Mockez les appels HTTP ; ne contactez pas l'API réelle dans les tests CI.
- Avant une PR : `make ci` (Ruff + pytest). La CI GitHub ajoute aussi **hassfest** et la **validation HACS**.

```bash
# Python aligné HA (3.14 = runtime actuel, 3.13 = plancher 2025.9)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.14

make install   # venv sur python3.14 (sinon 3.13)
make lint
make test
make ci
```
La CI valide **3.13** (HA 2025.9+) et **3.14** (HA 2026.x).
---

## Périmètre du projet

### Dans le scope

- Lecture des données optiFamily utiles à la domotique
- Capteurs, automatisations, notifications
- Robustesse (gestion erreurs, ré-authentification)
- Sécurité et respect de la vie privée

### Hors scope (sauf décision contraire)

- Modification de données optiFamily (planning, messages, etc.)
- Exposition de données financières ou personnelles sensibles
- Reverse engineering agressif de l'API
- Contournement de l'authentification

---

## Code de conduite

- Soyez respectueux et constructif.
- Acceptez les retours de revue de code.
- Privilégiez la simplicité et la maintenabilité.
- Pensez aux autres parents qui utiliseront cette intégration avec leurs données personnelles.

---

## Questions

Pour toute question, ouvrez une [issue](https://github.com/jokod/ha-optifamily/issues) plutôt qu'un message privé, afin que la réponse profite à toute la communauté.

Merci pour votre contribution !
