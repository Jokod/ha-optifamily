# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Versionnement Sémantique](https://semver.org/lang/fr/).

## [Unreleased]

## [1.0.7] - 2026-09-04

### Added
- Transmissions : contenu détaillé exposé (`items`, `lignes`, `markdown`) sur le capteur du jour
- Capteur **Journal transmissions** + services `optifamily.set_transmissions_date` / `shift_transmissions_date`
- Tableau de bord : détail du jour sur Accueil + onglet **Transmissions** (navigation jour par jour)
- Documents : endpoints famille et enfant (agrégés dans le compteur Documents)
- Option **pause nocturne** des mises à jour (défaut 21:00 → 06:00, désactivable / horaires réglables)

## [1.0.6] - 2026-09-04

### Fixed
- Appareils enfants : `via_device` remplacé par `via_device_id` (dépréciation HA, retrait en 2027.8)
- Tableau de bord : condition Lovelace des raccourcis package — `state` à la place de `template` (non supporté)

## [1.0.5] - 2026-09-04

### Added
- Package helpers : phase journée (`maison` / `deposer` / `creche` / `chercher` / `rentre`), capteur attention, silencieux planifié, scripts résumé / bascule
- Blueprint **Rappel créneau** (déposer / chercher selon horaires, anticipation configurable)
- Mode silencieux optionnel sur les blueprints notification / rappels / bilan / résumé
- Tableau de bord : chip phase, raccourcis silencieux / attention / résumé, section transmissions (si > 0)

### Changed
- Tableaux de bord : `week-planner-card` compact déplacé sur **Aujourd’hui** (remplace l’aperçu markdown) ; vue Planning retirée (3 onglets)
- Événements « Fermeture » : trait vertical rouge sur le planning semaine
- Rappels famille / matin : variables blueprint corrigées (`trigger_variables` au lieu de `input.*` dans les templates)

## [1.0.4] - 2026-09-03

### Added
- Attribut `optifamily_kind` sur les capteurs Transmissions et Albums (découverte auto dans les tableaux de bord)
- Dépendance Lovelace documentée : `week-planner-card` (vue Planning)

### Changed
- Tableaux de bord refondus (FR + EN) en 4 vues : Aujourd’hui, Enfants, Planning (`week-planner-card`), Calendrier (mois)
- Bandeau Aujourd’hui : textes contextuels selon l’heure (déposer / en crèche / aller chercher / rentré) ; synchro uniquement sur le badge
- Cartes présence : icônes et libellés alignés sur la phase du créneau

### Fixed
- Tableaux de bord / package helpers : `selectattr` sur `optifamily_kind` ne plante plus sur les capteurs sans cet attribut (`ReadOnlyDict`)
- Comparaison de dates naive vs aware (planning 7 jours + calendrier)
- Calendrier : plus de créneaux en double (semaines API qui se chevauchent / jours hors mois)
- Entity ID fixe `calendar.optifamily_planning` pour le calendrier famille

## [1.0.3] - 2026-09-03

### Added
- Calendrier Home Assistant (`calendar.optifamily_planning`) pour naviguer les créneaux mois par mois
- Attribut `optifamily_kind` pour que les tableaux de bord trouvent les capteurs même si l’entity_id est préfixé du nom de crèche
- Cache planning calendrier (TTL 30 min, coalescing, retry 5 min) : changer de mois ne rejoue pas l’API
- Blueprints copiés automatiquement vers `config/blueprints` au setup (HACS n’installe pas la racine `blueprints/`)
- Blueprints album, facture, document et actualité

### Changed
- Créneaux du jour affichés en texte (`07:45 - 18:45`) au lieu d’un dump YAML
- Capteur « Dernier rafraîchissement » : horodatage réel (`last_sync_at`) au lieu du booléen HA `last_update_success` (affichage « Indisponible »)
- Tableaux de bord : un YAML français et un anglais (`dashboards/optifamily.fr.yaml`, `optifamily.en.yaml`)
- Désinstallation : tokens + blueprints copiés (si plus aucune entrée OptiFamily) ; suppression nominative uniquement (pas de `rmtree` du dossier)
- Erreurs API : 403 → ré-auth, corps JSON `message` extrait, timeouts/`ClientError` unifiés, formes de réponse anormales normalisées, 401 polling → reconfiguration HA

## [1.0.2] - 2026-09-03

### Changed
- Capteur « Messages non lus » remplacé par deux capteurs : crèche (`sender=false`) et moi (`sender=true`), avec attributs `origine`, `total`, `non_lus`, `last_message_date`, `last_unread_date`

### Added
- Badge GitHub Release dans le README

## [1.0.1] - 2026-09-03

### Fixed
- Crash au setup : `persisted_enfants` manquant dans `__slots__` de `OptieFamilyData`

### Added
- Intervalle de polling configurable (défaut 30 min, mini 5, maxi 120)
- Capteur diagnostic « Dernier rafraîchissement »
- Coverage tests à 100 %

## [1.0.0] - 2026-09-03

### Added
- Première version publique
