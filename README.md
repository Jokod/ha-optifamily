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
| Messages non lus (crèche) | Messages reçus de la crèche non lus |
| Messages non lus (moi) | Messages que vous avez envoyés encore non lus |
| Actualités / Documents / Factures | Compteurs utiles pour des notifications |

### Par enfant (un appareil Home Assistant chacun)

| Capteur | Utilité |
|---|---|
| Présent aujourd’hui | `présent` / `absent` / `inconnu` |
| Créneaux ce mois | Nombre de créneaux réguliers |
| Transmissions du jour | Nouvelles transmissions |
| Albums | Nombre d’albums photos |

Les noms exacts des entités dépendent des prénoms (ex. `sensor.lea_present_aujourd_hui`).

---

## Automatisations & tableau de bord

### Blueprints inclus

Après installation, dans **Paramètres → Automatisations & scènes → Blueprints**  
(ou copiez `blueprints/` vers `config/blueprints/`) :

| Blueprint | Type | Idée |
|---|---|---|
| Nouveau message | Automation | Dès qu’un message non lu arrive |
| Messages (seuil) | Automation | Alerte si le compteur dépasse N |
| Rappel crèche famille | Automation | Rappel matinal pour tous les enfants |
| Rappel crèche matin | Automation | Rappel pour un enfant précis |
| Changement de présence | Automation | Notifie présent ↔ absent |
| Transmissions du jour | Automation | Nouvelles transmissions (par enfant) |
| Bilan du soir | Automation | Résumé familial le soir |
| Résumé famille | **Script** | Résumé à la demande (bouton / autre auto) |

### Tableaux de bord

| Fichier | Niveau |
|---|---|
| `dashboards/optifamily.yaml` | Vue simple |
| `dashboards/optifamily_avance.yaml` | Vues Aujourd’hui / Détail / Historique, cartes conditionnelles |

Import : **Paramètres → Tableaux de bord → Ajouter → Importer YAML**, puis adaptez les `entity_id`.

### Package helpers (optionnel)

`packages/optifamily_helpers.yaml` ajoute :

- un **mode silencieux** (`input_boolean`)
- un **capteur résumé texte**
- un **script** d’envoi du résumé

Activation typique dans `configuration.yaml` :

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Puis copiez le fichier dans `config/packages/` et adaptez les entités.

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
- Les contenus détaillés des messages/transmissions ne sont pas tous exposés (compteurs et présence avant tout).

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
