# Guide d’utilisation OptiFamily

L’intégration fournit des **données** (capteurs, calendriers, services) dans Home Assistant.  
**Rien n’impose un tableau de bord** : vous pouvez n’utiliser que les entités, vos propres cartes, des automations, ou le dashboard d’exemple fourni.

> Doc technique API (contributeurs) : [API.md](API.md)  
> Install / HACS : [README](../README.md)

---

## 1. Philosophie

| Couche | Rôle | Obligatoire ? |
|--------|------|----------------|
| Intégration HACS | Capteurs, calendriers, services | **Oui** (cœur) |
| Blueprints | Modèles d’automations / script | Non — à créer si besoin |
| Package helpers | Mode silencieux + scripts confort | Non |
| Thème `optifamily` | Largeur des sections Lovelace | Non |
| Dashboard YAML d’exemple | UI prête à importer | Non — **facultatif** |
| Cartes HACS (Mushroom…) | Seulement si vous importez l’exemple | Non |

**Recommandation** : configurez l’intégration, explorez **Paramètres → Appareils & Services → OptiFamily**, puis construisez l’affichage qui vous convient.

---

## 2. Trouver les bonnes entités (`optifamily_kind`)

Les `entity_id` dépendent du nom de la crèche / des prénoms  
(ex. `sensor.ma_creche_phase_journee`, `sensor.lea_present_aujourd_hui`).

Toutes les entités OptiFamily portent un attribut **`optifamily_kind`**.  
En multi-crèche, filtrez aussi **`config_entry_id`**.

### Jinja — première entité d’un kind

```jinja
{% set s = states.sensor
  | selectattr('attributes', 'contains', 'optifamily_kind')
  | selectattr('attributes.optifamily_kind', 'eq', 'phase_journee')
  | list %}
{{ s[0].entity_id if s else none }}
```

### Lovelace — auto-entities (exemple)

```yaml
type: custom:auto-entities
card:
  type: entities
filter:
  include:
    - attributes:
        optifamily_kind: present
```

### Developer tools

**Outils de développement → États** : chercher `optifamily_kind` dans les attributs.

Attributs de scope utiles partout : `config_entry_id`, `creche_id`, `creche_name`.

---

## 3. Catalogue des données

### 3.1 Capteurs famille (appareil crèche / hub)

| `optifamily_kind` | État | Données utiles pour l’affichage |
|-------------------|------|----------------------------------|
| `enfants` | nombre suivis | `liste`, `presents_aujourdhui`, `noms_presents` |
| `enfants_presents` | nb présents aujourd’hui | `noms`, `liste` |
| `phase_journee` | `maison` · `deposer` · `creche` · `chercher` · `rentre` · `ferme` · `inconnu` | `libelle`, `message`, `minutes`, `cible`, `attention`, `attention_raison`, `enfants[]` |
| `resume` | message **court** (bandeau) | **`texte`** (notif / résumé long), **`lignes`**, `phase`, `libelle`, `attention*` |
| `attention` *(binary_sensor)* | `on` = à regarder | `raison`, `phase`, `message` — messages crèche non lus **ou** dépôt/récup ≤ 90 min |
| `messages` | total | `non_lus`, `non_lus_creche`, `non_lus_moi`, `items[]` (`corps`, `vu`, `sender`, `origine`…) |
| `messages_unread_creche` | nb | `items[]`, `origine=creche` |
| `messages_unread_me` | nb | `items[]`, `origine=moi` |
| `creche` | nom | `adresse`, `telephone`, `email`, `description`, `photos`, `collaborateurs` |
| `actualites_total` | compteur | `items[]` (`titre`, `date`, `resume`) |
| `documents_total` | somme scopes | `creche`, `famille`, `enfants`, `items_*` |
| `documents` | nb du **scope courant** | `scope`, `enfant_id`, `enfant_libelle`, `items[]` — voir service `set_documents_scope` |
| `facturation_total` | nb | `items[]` (téléchargeables) |
| `dernier_rafraichissement` | horodatage | `intervalle_minutes` (diagnostic) |

### 3.2 Capteurs par enfant (un device HA / enfant)

| `optifamily_kind` | État | Données utiles |
|-------------------|------|----------------|
| `present` | `présent` / `absent` / `inconnu` | `enfant_id`, `enfant_libelle`, `statut_jour`, `phase_enfant`, `plages[]`, `debut`/`fin`, `minutes`, `message`, `creneaux*` |
| `planning_slots` | nb créneaux du mois | `jours`, `previous`, `next`, `label` |
| `transmissions` | nb **aujourd’hui** | `items[]`, `lignes`, `markdown`, **`stats`**, `date_fr` |
| `transmissions_journal` | nb date naviguée | idem + date via services journal |
| `albums` | nb | `items[]` (album + `photos[]`) |

### 3.3 Attribut `stats` (transmissions)

Objet typique :

| Clé | Contenu |
|-----|---------|
| `total` | nombre d’événements |
| `by_type` | compteurs par type brut |
| `biberons` / `biberons_ml` | biberons |
| `repas` | repas |
| `siestes` / `siestes_minutes` | siestes |
| `changes` / `changes_pipi` / `changes_caca` | changes |
| `arrivee` / `depart` | horaires affichés |
| `resume` | phrase FR prête à afficher |

Exemple :

```jinja
{{ state_attr(entity_id, 'stats').resume }}
{{ state_attr(entity_id, 'stats').biberons_ml }}
```

### 3.4 Calendriers

| `optifamily_kind` | `entity_id` | Usage |
|-------------------|-------------|--------|
| `planning_family` | `calendar.optifamily_planning_<8caractères>` | planning famille (carte calendrier HA, week planner…) |
| `planning` | selon prénom | créneaux d’un enfant |

---

## 4. Services

Domaine : `optifamily`

| Service | Paramètres | Effet |
|---------|------------|--------|
| `refresh` | `config_entry_id?` | Sync API immédiate (ignore pause nuit / fermée) |
| `set_transmissions_date` | `date?` (YYYY-MM-DD, défaut = aujourd’hui), `config_entry_id?` | Charge le journal |
| `shift_transmissions_date` | `days` (−30…30), `config_entry_id?` | Décale la date du journal |
| `set_documents_scope` | `scope` = `creche`\|`famille`\|`enfant`, `enfant_id?` | Filtre le capteur `documents` |
| `download` | `kind` = `photo`\|`document`\|`facture`, `id`, … | Fichier dans `config/www/optifamily/` → `/local/optifamily/...` |

Événements bus (download) : `optifamily_download_ready`, `optifamily_download_failed`.

---

## 5. Afficher sans le dashboard fourni

Tout ce qui suit utilise **uniquement** les entités natives.

### Carte entités (stock)

```yaml
type: entities
entities:
  - sensor.ma_creche_phase_journee
  - binary_sensor.ma_creche_attention
  - sensor.lea_present_aujourd_hui
```

### Markdown + attributs

```yaml
type: markdown
content: |
  ## {{ state_attr('sensor.xxx_resume', 'libelle') }}
  {{ state_attr('sensor.xxx_resume', 'texte') }}
```

### Mushroom (si déjà installé chez vous)

```yaml
type: custom:mushroom-template-card
primary: "{{ states(entity) }}"
secondary: "{{ state_attr(entity, 'message') }}"
entity: sensor.lea_present_aujourd_hui
```

### Notification avec le résumé long

```yaml
action: notify.persistent_notification
data:
  title: "OptiFamily"
  message: "{{ state_attr(resume_entity, 'texte') }}"
```

(`resume_entity` = capteur `optifamily_kind: resume`)

### Badge / chip conditionnel

- Présence : état `present`
- Urgence visuelle : `binary_sensor` `attention` = `on`
- Phase : icône selon `phase_journee` (`deposer`, `chercher`, …)

---

## 6. Automations

### Blueprints (optionnels)

Copiés dans `config/blueprints/.../optifamily/` après install.  
Ils **n’agissent pas** tant que vous ne créez pas une automation / un script depuis le blueprint.

Idées couvertes : nouveau message, seuil messages, album, facture, document, actualité, transmissions, rappels créneau / matin, présence, bilan soir, script résumé.

### Sans blueprint

Déclencheurs classiques : `state` sur compteurs, `numeric_state` sur présents, `time` + condition phase, etc.  
Exemples courts dans le [README](../README.md).

---

## 7. Extras optionnels livrés avec l’intégration

### Package helpers (silencieux)

- Fichier recopié : `config/packages/optifamily_helpers.yaml` (écrasé à chaque maj)
- À activer **une fois** :
  ```yaml
  homeassistant:
    packages: !include_dir_named packages
  ```
- Fournit : `input_boolean.optifamily_quiet_hours`, silencieux auto, scripts notify / toggle  
- **Ignorez-le** si vous gérez vos notifications autrement

### Thème

- Copié dans `config/themes/optifamily.yaml` (layout sections, neutre)
- Utile seulement si vous chargez les thèmes HA et voulez ce fichier

### Dashboard d’exemple (facultatif)

- Copié dans `config/optifamily/dashboards/optifamily.yaml`
- **À importer manuellement** si vous le souhaitez
- Nécessite alors des cartes HACS Frontend (Mushroom, card-mod, auto-entities, layout-card)
- Vous pouvez **ne jamais l’importer** et rester sur vos cartes

Suppression de la **dernière** instance OptiFamily : retrait des copies (blueprints, thème, package, fichier dashboard).

---

## 8. Options de l’intégration

**Configurer** l’entrée OptiFamily :

| Option | Défaut | Effet |
|--------|--------|--------|
| Intervalle | 30 min | Polling API (5–120 min) |
| Pause nocturne | oui | Pas d’API la nuit (premier load OK) |
| Début / fin pause | 21:00 / 06:00 | Heure locale HA |
| Pause si crèche fermée | oui | Moins d’appels hors jours utiles |
| Enfants suivis | tous | Exclus = plus de polling + purge devices |

Service `optifamily.refresh` force une sync même pendant une pause.

---

## 9. Multi-crèche

- Une **config entry** = une crèche
- Filtrer Lovelace / templates avec `config_entry_id`
- Calendrier famille : `calendar.optifamily_planning_<8 premiers caractères de l’entry_id en minuscules>`

---

## 10. Confidentialité & limites

- Lecture seule côté optiFamily
- Identifiants / tokens locaux à HA
- Pas d’écriture de planning
- API non officielle : peut évoluer

---

## 11. Dépannage rapide

| Symptôme | Piste |
|----------|--------|
| Entité `unknown` | Attendre un refresh ou appeler `optifamily.refresh` |
| Mauvais enfant / trop d’enfants | Options → Enfants suivis |
| Journal vide autre jour | `set_transmissions_date` / `shift_transmissions_date` |
| Docs pas le bon scope | `set_documents_scope` |
| Package helpers absent | `packages: !include_dir_named packages` + redémarrage |

Logs :

```yaml
logger:
  default: warning
  logs:
    custom_components.optifamily: debug
```
