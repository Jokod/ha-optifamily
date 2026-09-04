# OptiFamily — Intégration Home Assistant (HACS)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9%2B-41BDF5.svg?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Jokod/ha-optifamily?include_prereleases&label=Release&logo=github)](https://github.com/Jokod/ha-optifamily/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/Jokod/ha-optifamily/ci.yml?branch=main&label=CI&logo=github)](https://github.com/Jokod/ha-optifamily/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.13%2B%20(3.14%20HA%20actuel)-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

Intégration **open-source non officielle** pour Home Assistant : suivez la présence en crèche, les messages et les transmissions de vos enfants depuis votre maison connectée.

Compatible **un ou plusieurs enfants**, et **plusieurs crèches** (une instance d’intégration par crèche).

---

## Installation rapide

[![Ajouter le dépôt dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jokod&repository=ha-optifamily&category=integration)

[![Configurer OptiFamily](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=optifamily)

> Nécessite [HACS](https://hacs.xyz/) et [my.home-assistant.io](https://my.home-assistant.io/).

---

## Avertissement

> **Cette intégration est un projet open-source non officiel et n'est ni affiliée à, ni soutenue par THEMISTO CONSEIL / optiCrèche. Elle utilise le compte personnel de l'utilisateur pour accéder aux données auxquelles celui-ci a accès via le portail optiFamily.**

- Lecture seule : rien n’est modifié côté optiFamily.
- L’API utilisée n’est pas documentée officiellement et peut évoluer.
- Vous restez responsable de vos identifiants dans Home Assistant.

---

## Prérequis

- Home Assistant **2025.9** ou plus récent (fenêtre ~1 an ; testé jusqu’à **2026.9**)
- Un compte parent **optiFamily**
- HACS (recommandé)

Vous n’avez **pas** besoin de connaître l’identifiant de votre crèche ni ceux de vos enfants : ils sont détectés automatiquement.

---

## Installation

### Via HACS (recommandé)

1. Ouvrez **HACS → Intégrations**.
2. Menu **⋮ → Dépôts personnalisés**.
3. Ajoutez `https://github.com/jokod/ha-optifamily` (catégorie **Intégration**).
4. Recherchez **OptiFamily** → **Télécharger**.
5. **Redémarrez** Home Assistant.

### Installation manuelle

1. Copiez `custom_components/optifamily` dans `config/custom_components/` de votre HA.
2. Redémarrez Home Assistant.

---

## Configuration

Il suffit de votre **e-mail** et **mot de passe** optiFamily.

### Depuis l’interface

1. **Paramètres → Appareils & Services → Ajouter une intégration**
2. Recherchez **OptiFamily**
3. Saisissez e-mail et mot de passe

Si plusieurs crèches sont liées à votre compte, choisissez celle à utiliser.  
Pour une deuxième crèche : ajoutez à nouveau l’intégration et sélectionnez l’autre crèche.

### Via secrets (optionnel)

Dans `secrets.yaml` :

```yaml
optifamily_username: "votre.email@example.com"
optifamily_password: "votre_mot_de_passe"
```

Dans `configuration.yaml` :

```yaml
optifamily:
  username: !secret optifamily_username
  password: !secret optifamily_password
```

Puis redémarrez Home Assistant.

---

## Ce que vous obtenez

### Vue famille (appareil global)

| Capteur | Utilité |
|---|---|
| Enfants | Nombre d’enfants suivis |
| Enfants en crèche aujourd’hui | Combien d’enfants sont prévus aujourd’hui (+ leurs prénoms) |
| Phase journée | `maison` · `deposer` · `creche` · `chercher` · `rentre` · `ferme` · `inconnu` |
| Résumé journée | Message FR contextuel (hero dashboard) |
| Attention | Binary sensor « problème » si messages non lus ou dépôt/récupération ≤ 90 min |
| Messages non lus (crèche) | Messages reçus + `items[]` (corps) |
| Messages non lus (moi) | Messages envoyés encore non lus |
| Actualités / Documents / Factures | Compteurs + `items[]` riches (téléchargement docs/factures) |

### Par enfant (un appareil Home Assistant chacun)

| Capteur | Utilité |
|---|---|
| Présent aujourd’hui | `présent` / `absent` / `inconnu` + `statut_jour`, `plages`, `phase_enfant`, `message` |
| Créneaux ce mois | Nombre de créneaux réguliers |
| Transmissions du jour | Compteur + timeline (cartes sieste / change / repas…) |
| Journal transmissions | Même timeline pour une date naviguable |
| Albums | Nombre d’albums + photos (`items[]`, download) |

Les noms exacts des entités dépendent du **nom de la crèche** et des prénoms
(ex. `sensor.ma_creche_enfants`, `sensor.lea_present_aujourd_hui`).
Les tableaux de bord fournis retrouvent tout seuls les capteurs via l’attribut `optifamily_kind`
(et `config_entry_id` en multi-crèche).

Un **calendrier famille** par entry (`calendar.optifamily_planning_<entry8>`) alimente
l’aperçu semaine et l’onglet **Calendrier**.

Dans **Configurer** l’intégration : multi-select **Enfants suivis** — les exclus sont
retirés du suivi (plus de polling enfant) et leurs devices/entités sont purgés.
---

## Automatisations & tableau de bord

### Blueprints inclus

Après installation **HACS** (et un redémarrage), les blueprints sont copiés automatiquement dans `config/blueprints/automation/optifamily/` et `config/blueprints/script/optifamily/`. Ils apparaissent dans **Paramètres → Automatisations & scènes → Blueprints**. À la suppression de la **dernière** instance OptiFamily, ces fichiers copiés sont retirés.

| Blueprint | Type | Idée |
|---|---|---|
| Nouveau message | Automation | Message non lu (choisir le capteur **crèche**) |
| Messages (seuil) | Automation | Alerte si le compteur dépasse N |
| Nouvel album / photos | Automation | Nouvel album (par enfant) |
| Nouvelle facture | Automation | Compteur factures en hausse |
| Nouveau document | Automation | Compteur documents en hausse |
| Nouvelle actualité | Automation | Compteur actualités en hausse |
| Transmissions du jour | Automation | Nouvelles transmissions (par enfant) |
| Rappel crèche famille | Automation | Rappel matinal pour tous les enfants |
| Rappel crèche matin | Automation | Rappel pour un enfant précis |
| Rappel créneau | Automation | Déposer / chercher selon horaires (anticipation) |
| Changement de présence | Automation | Notifie présent ↔ absent |
| Bilan du soir | Automation | Résumé familial le soir |
| Résumé famille | **Script** | Résumé à la demande (bouton / autre auto) |

### Tableau de bord

Fichier unique FR : [`dashboards/optifamily.yaml`](dashboards/optifamily.yaml).

Import : **Paramètres → Tableaux de bord → Ajouter → Importer YAML**.
Les cartes détectent l’intégration automatiquement (`optifamily_kind`).
En multi-crèche : **un dashboard par entry** (filtre `config_entry_id`).

Les vues sont en **panel plein largeur**. Le thème `optifamily` (tokens
`--optifamily-*` pour card-mod) est **copié automatiquement** dans `config/themes/`.
Une fois : `frontend:` → `themes: !include_dir_merge_named themes` dans
`configuration.yaml`, puis recharger les thèmes.

Cartes Lovelace HACS à installer **à la main** (HACS → Frontend). L’intégration **ne les installe pas**.

| Carte | Dépôt |
|---|---|
| Mushroom | [lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) |
| card-mod | [lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) |
| auto-entities | [lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities) |
| week-planner-card | [week-planner-card](https://github.com/FamousWolf/week-planner-card) |
| layout-card (mod-card) | [lovelace-layout-card](https://github.com/thomasloven/lovelace-layout-card) |

Onglets : **Accueil**, **Enfants**, **Transmissions**, **Médias** (albums + documents), **Infos** (actualités / factures / messages). Sans ces plugins, l’import affiche « custom element doesn’t exist ».

Services : `optifamily.set_transmissions_date` / `shift_transmissions_date`,
`optifamily.set_documents_scope` (`creche` \| `famille` \| `enfant`),
`optifamily.download` (photo / document / facture → `/local/optifamily/...`).


### Package helpers (optionnel)

`packages/optifamily_helpers.yaml` = **confort notifications uniquement**
(plus de logique métier phase/attention — celle-ci vit dans l’intégration) :

| Élément | Rôle |
|---|---|
| `input_boolean.optifamily_quiet_hours` | Mode silencieux (branchable sur les blueprints) |
| `input_boolean.optifamily_quiet_auto` + horaires | Silencieux automatique (défaut 21:00 → **06:00**) |
| `script.optifamily_notify_resume` | Envoie le résumé via les capteurs d’intégration |
| `script.optifamily_toggle_quiet` | Bascule le mode silencieux |

Activation typique dans `configuration.yaml` :

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Puis copiez le fichier dans `config/packages/`.

### Migration depuis 1.0.x

1. Mettre à jour l’intégration HACS → redémarrer HA
2. Recharger les thèmes
3. Remplacer/re-importer `dashboards/optifamily.yaml`
4. Mettre à jour le package helpers (sinon doublons phase/attention templates)
5. Si 2ᵉ crèche : vérifier le nouvel `entity_id` calendrier famille
6. Re-binder les blueprints sur phase / résumé si besoin

### Exemple YAML : notification message non lu

```yaml
automation:
  - alias: "OptiFamily - Nouveau message"
    trigger:
      - platform: state
        entity_id: sensor.optifamily_messages_non_lus_creche
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "OptiFamily"
          message: "Vous avez {{ states('sensor.optifamily_messages_non_lus_creche') }} message(s) de la crèche non lu(s)."
```

### Exemple : rappel matinal (tous les enfants)

```yaml
automation:
  - alias: "OptiFamily - Crèche ce matin"
    trigger:
      - platform: time
        at: "07:30:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.optifamily_enfants_en_creche_aujourd_hui
        above: 0
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "Crèche"
          message: >
            {{ states('sensor.optifamily_enfants_en_creche_aujourd_hui') }} enfant(s) :
            {{ state_attr('sensor.optifamily_enfants_en_creche_aujourd_hui', 'noms') | join(', ') }}.
```

---

## Options

**Paramètres → Appareils & Services → OptiFamily → Configurer**

| Option | Défaut | Description |
|---|---|---|
| Intervalle de mise à jour | **30 minutes** | Entre 5 et 120 minutes (réglable) |
| Pause nocturne | **activée** | Pas d’appel API pendant la plage (le premier chargement reste toujours fait) |
| Début de la pause | **21:00** | Heure locale Home Assistant |
| Fin de la pause | **06:00** | Les mises à jour reprennent à partir de cette heure |

Capteur diagnostic : `Dernier rafraîchissement` (horodatage du dernier polling réussi + intervalle en attributs).

---

## Confidentialité

- Mot de passe et tokens restent dans Home Assistant (stockage local).
- Aucune donnée bancaire / allocataire / IBAN n’est exposée dans les capteurs.
- L’intégration ne journalise pas les réponses API complètes.
- Mode **lecture seule** uniquement.

Ne partagez jamais vos logs bruts (identifiants, tokens, données personnelles).

---

## Limitations

- Dépend d’une API non officielle (peut casser en cas de changement côté optiFamily).
- Pas d’écriture (pas de modification de planning depuis Home Assistant).
- Les contenus détaillés des messages ne sont pas tous exposés (compteurs avant tout) ; les **transmissions du jour** le sont (détail + journal).

---

## Dépannage

| Problème | Que faire |
|---|---|
| Identifiants invalides | Vérifiez e-mail et mot de passe optiFamily |
| Impossible de se connecter | Vérifiez que Home Assistant a accès à Internet |
| Capteur « inconnu » | Attendez le prochain rafraîchissement (quelques minutes) |
| Aucun enfant | Vérifiez sur le portail optiFamily que des enfants sont bien rattachés |
| Plusieurs crèches | Ajoutez l’intégration une fois par crèche |

Logs de diagnostic (sans données sensibles) :

```yaml
logger:
  default: warning
  logs:
    custom_components.optifamily: debug
```

---

## Aide & contribution

- Questions / bugs : [Issues GitHub](https://github.com/jokod/ha-optifamily/issues)
- Pour contribuer au code : voir [CONTRIBUTING.md](CONTRIBUTING.md)
- Documentation technique (contributeurs) : [docs/](docs/)

---

## Licence

MIT — voir [LICENSE](LICENSE).
