# OptiFamily — Intégration Home Assistant (HACS)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9%2B-41BDF5.svg?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Jokod/ha-optifamily?include_prereleases&label=Release&logo=github)](https://github.com/Jokod/ha-optifamily/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/Jokod/ha-optifamily/ci.yml?branch=main&label=CI&logo=github)](https://github.com/Jokod/ha-optifamily/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.13%2B%20(3.14%20HA%20actuel)-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

Intégration **open-source non officielle** pour Home Assistant : suivez la présence en crèche, les messages et les transmissions de vos enfants depuis votre maison connectée.

Compatible **un ou plusieurs enfants**, et **plusieurs crèches** (une instance d’intégration par crèche).

**Doc complète (données, attributs, affichage, services)** → [docs/GUIDE.md](docs/GUIDE.md)  
L’intégration fournit les **données** ; le tableau de bord d’exemple est **facultatif** — vous pouvez n’utiliser que vos cartes / automations.

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

Capteurs famille (phase, résumé, messages, crèche, docs, factures…), capteurs **par enfant** (présence, transmissions, albums…), calendriers, et services (`refresh`, journal, documents, download).

Inventaire détaillé des `optifamily_kind`, attributs (`texte`, `stats`, `items[]`…) et exemples de cartes : **[Guide d’utilisation](docs/GUIDE.md)**.

Les noms d’entités dépendent de la crèche / des prénoms. Pour les retrouver : attribut **`optifamily_kind`** (et `config_entry_id` en multi-crèche).

Dans **Configurer** : multi-select **Enfants suivis** — les exclus sont retirés du suivi et purgés.

---

## Extras optionnels

Rien de tout ceci n’est requis pour utiliser les données.

| Extra | Rôle | Obligatoire |
|-------|------|-------------|
| Blueprints | Modèles d’automations (à créer soi-même depuis le blueprint) | Non |
| Package helpers | Mode silencieux + scripts confort (`config/packages/…`) | Non |
| Thème | Largeur sections Lovelace | Non |
| **Dashboard d’exemple** | YAML prêt à importer — **à vous de décider** | Non |

Détail (activation packages, import dashboard, cartes HACS si vous choisissez l’exemple) : [Guide §7](docs/GUIDE.md#7-extras-optionnels-livrés-avec-lintégration).

---

## Exemples d’automations

### Notification message non lu

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

### Rappel matinal (tous les enfants)

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
| Pause si crèche fermée | **activée** | Moins d’appels hors jours utiles |

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
- Les messages et transmissions exposent un état + attributs riches (`items[]`, `stats`, `texte`…) — voir le [Guide](docs/GUIDE.md).

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
- Guide utilisateur (données & affichage) : [docs/GUIDE.md](docs/GUIDE.md)
- Pour contribuer au code : voir [CONTRIBUTING.md](CONTRIBUTING.md)
- API optiFamily (contributeurs) : [docs/API.md](docs/API.md)

---

## Licence

MIT — voir [LICENSE](LICENSE).
